"""Opt-in smoke test against a running Resolve in-app bridge."""

import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.core import db
from app.editing.adapter import execute_operation
from app.editing.registry import default_registry
from app.main import app


@pytest.mark.skipif(os.environ.get("GHS_RESOLVE_LIVE") != "1", reason="requires live Resolve and creates a test project")
def test_resolve_free_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{tmp_path / 'resolve.db'}"))
    suffix = uuid4().hex[:10]
    output = Path.home() / "Movies" / f"ghs-resolve-{suffix}"
    output.mkdir(parents=True)
    source = output / "source.mov"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24",
        "-t", "2", "-c:v", "dnxhd", "-profile:v", "dnxhr_lb", str(source),
    ], check=True, timeout=30)
    with TestClient(app) as api:
        url = "/api/plugins/davinci-resolve"
        assert api.post(f"{url}/install", json={"confirm_permissions": True}).status_code == 200
        connected = api.post(f"{url}/connect")
        assert connected.status_code == 200, connected.text
        assert connected.json()["plugin"]["connected"] is True
        assert any(check["id"] == "adapter-health" and check["status"] == "pass"
                   for check in api.post(f"{url}/diagnose").json()["checks"])
        assert api.post("/api/router/decide", json={"operation": "professional_edit"}).json()["selected"] is None
        assert api.get(f"{url}/tools").json()["tools"]
        adapter = default_registry.create("davinci-resolve")
        bridge = adapter.bridge
        previous = bridge.health()["current_project"]
        assert len(bridge.health()["operations"]) == 15
        try:
            def run(operation, **kwargs):
                return execute_operation(adapter, operation, kwargs)

            project = run("create_project", name=f"GHS Resolve {suffix}")
            assert bridge.named("get_project")["name"] == project["name"]
            media = run("import_media", paths=[str(source)])
            timeline = run("create_timeline", project_id=project["id"], name="GHS smoke")
            run("add_track", timeline_id=timeline["handle"], track={"type": "video"})
            run("add_clip", timeline_id=timeline["handle"], clip={"media_handle": media[0]["handle"], "start_frame": 0, "end_frame": 23, "track_index": 2, "media_type": "video"})
            items = bridge.call(timeline["handle"], "GetItemListInTrack", "video", 2)
            assert len(items) == 1
            assert bridge.named("save_project")["saved"] is True
            selected = api.post("/api/router/decide", json={"operation": "professional_edit"}).json()["selected"]
            assert selected["plugin_id"] == "davinci-resolve" and selected["executable"]
            assert bridge.call(project["id"], "SetCurrentRenderFormatAndCodec", "mov", "DNxHRLB") is True
            job = run("render_final", timeline_id=timeline["handle"], settings={"TargetDir": str(output), "CustomName": "result", "SelectAllFrames": True, "ExportVideo": True, "ExportAudio": False})
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                status = run("get_job_status", job_id=job["job_id"])
                if status["JobStatus"] in {"Complete", "Finalizado", "Failed", "Cancelled", "Fallido", "Cancelado"}:
                    break
                time.sleep(1)
            assert status["JobStatus"] in {"Complete", "Finalizado"} and status["CompletionPercentage"] == 100, status
            rendered = output / "result.mov"
            probe = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(rendered),
            ], timeout=15))
            assert any(stream["codec_type"] == "video" for stream in probe["streams"])
            assert float(probe["format"]["duration"]) > 0
            assert "render" in api.get(f"{url}/capabilities").json()["verified_capabilities"]
            print(f"{project['name']}: {rendered}, {probe['format']['duration']} s")
        finally:
            if previous:
                restored = bridge.call("project_manager", "LoadProject", previous)
                if isinstance(restored, dict) and restored.get("__handle__"):
                    bridge.named("release_handles", {"handles": [restored["__handle__"]]})
