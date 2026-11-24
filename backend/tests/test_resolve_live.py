"""Opt-in smoke test against a running Resolve in-app bridge."""

import json
import os
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.core import db
from app.editing.adapter import execute_operation
from app.editing.adapters.resolve import ResolveConverter
from app.editing.adapters.resolve_bridge import ResolveBridgeCallError, ResolveBridgeClient
from app.editing.registry import default_registry
from app.editing.timeline import Asset, AudioTrack, Clip, Project, VideoTrack
from app.main import app


class _SmokeProbe(ResolveBridgeClient):
    # Fixture setup, readback and cleanup only; the adapter retains its own list.
    _ALLOWED_CALL_METHODS = frozenset({
        "GetStartFrame", "GetTrackCount", "GetItemListInTrack", "GetDuration",
        "SetCurrentRenderFormatAndCodec", "LoadProject",
    })


def _probe(path):
    result = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,nb_read_frames:format=duration",
        "-of", "json", str(path),
    ], timeout=15))
    stream = result["streams"][0]
    return Fraction(stream["avg_frame_rate"]), int(stream["nb_read_frames"]), float(result["format"]["duration"])


@pytest.mark.skipif(os.environ.get("GHS_RESOLVE_LIVE") != "1", reason="requires live Resolve and creates a test project")
def test_resolve_free_end_to_end(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level("INFO")
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{tmp_path / 'resolve.db'}"))
    suffix = uuid4().hex[:10]
    output = Path.home() / "Movies" / f"ghs-resolve-{suffix}"
    output.mkdir(parents=True)
    source = output / "source.mov"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24",
        "-t", "2", "-c:v", "dnxhd", "-profile:v", "dnxhr_lb", str(source),
    ], check=True, timeout=30)
    source_probe = _probe(source)
    assert source_probe == (24, 48, 2.0)
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
        probe = _SmokeProbe()
        health = bridge.health()
        previous = health["current_project"]
        assert set(health["operations"]) == {
            "health", "list_projects", "get_project", "list_timelines", "get_timeline", "list_media",
            "get_render_formats", "save_project", "set_current_timeline", "call", "release_handles",
            "list_methods", "get_attribute", "shutdown", "reload",
        }
        with pytest.raises(ResolveBridgeCallError) as error:
            bridge.named("ghs_unknown_operation")
        assert error.value.bridge_code == "operation_not_allowed"
        notes = connected.json()["plugin"]["adapter_notes"]
        assert f"Versión: {health['version']}." in notes
        assert f"Edición detectada: {health['edition'].title()}." in notes
        assert any("puente interno" in note for note in notes)
        assert any("Integración frágil" in note for note in notes)
        print(f"health: {health['edition']} {health['version']}; 15 ops; {health['policy']}")
        print(f"ghs_unknown_operation -> {error.value.bridge_code}")
        try:
            def run(operation, **kwargs):
                return execute_operation(adapter, operation, kwargs)

            project = run("create_project", name=f"GHS Resolve {suffix}")
            assert bridge.named("get_project")["name"] == project["name"]
            media = run("import_media", paths=[str(source)])
            timeline = run("create_timeline", project_id=project["id"], name="GHS smoke")
            unified = Project(
                name="GHS source of truth", metadata={"fps": 24},
                assets=[Asset(id="source", name=source.name, path=str(source), duration_seconds=2)],
                tracks=[VideoTrack(name="V1"), AudioTrack(name="A1"), VideoTrack(name="V2", clips=[
                    Clip(asset_id="source", duration_seconds=1),
                ])],
            )
            converter = ResolveConverter()
            plan = converter.convert(unified)
            assert plan.complete
            handle = timeline["handle"]
            start = probe.call(handle, "GetStartFrame")
            for track in plan.payload["tracks"]:
                while probe.call(handle, "GetTrackCount", track["kind"]) < track["index"]:
                    run("add_track", timeline_id=handle, track={"kind": track["kind"]})
                for clip in track["clips"]:
                    placement = converter.clip_placement(track, clip, source_fps=float(source_probe[0]), timeline_start=start)
                    run("add_clip", timeline_id=handle, clip={"media_handle": media[0]["handle"], **placement})
            assert (placement["start_frame"], placement["end_frame"], placement["track_index"]) == (0, 24, 2)
            v1 = probe.call(handle, "GetItemListInTrack", "video", 1) or []
            v2 = probe.call(handle, "GetItemListInTrack", "video", 2) or []
            assert not v1 and len(v2) == 1
            duration = probe.call(v2[0]["__handle__"], "GetDuration")
            assert duration == 24
            assert bridge.named("save_project")["saved"] is True
            selected = api.post("/api/router/decide", json={"operation": "professional_edit"}).json()["selected"]
            assert selected["plugin_id"] == "davinci-resolve" and selected["executable"]
            assert probe.call(project["id"], "SetCurrentRenderFormatAndCodec", "mov", "DNxHRLB") is True
            job = run("render_final", timeline_id=timeline["handle"], settings={"TargetDir": str(output), "CustomName": "result", "SelectAllFrames": True, "ExportVideo": True, "ExportAudio": False})
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                status = run("get_job_status", job_id=job["job_id"])
                if status["JobStatus"] in {"Complete", "Finalizado", "Failed", "Cancelled", "Fallido", "Cancelado"}:
                    break
                time.sleep(1)
            assert status["JobStatus"] in {"Complete", "Finalizado"} and status["CompletionPercentage"] == 100, status
            render_probe = _probe(output / "result.mov")
            assert render_probe == (24, 24, 1.0)
            caps = api.get(f"{url}/capabilities")
            assert "render" in caps.json()["verified_capabilities"]
            audit = api.get(f"{url}/audit")
            assert audit.json()["entries"]
            view = api.get(url)
            diagnosis = api.post(f"{url}/diagnose")
            captured = capsys.readouterr()
            surfaces = [captured.out, captured.err, caplog.text, connected.text, caps.text, audit.text,
                        view.text, diagnosis.text]
            if any(bridge.config["token"] in surface for surface in surfaces):
                pytest.fail("Se detectó la credencial en una superficie de salida.", pytrace=False)
            print(captured.out, end="")
            print("Credential check: absent from captured logs, audit and UI API payloads")
            print(f"{output}: source=48 frames/2.000000 s; render=24 frames/1.000000 s; 24 fps")
            print(f"Unified {track['name']} -> video trackIndex={placement['track_index']}; "
                  f"Resolve V1={len(v1)}, V2={len(v2)}, V2 clip duration={duration} frames")
        finally:
            if previous:
                restored = probe.call("project_manager", "LoadProject", previous)
                if isinstance(restored, dict) and restored.get("__handle__"):
                    bridge.named("release_handles", {"handles": [restored["__handle__"]]})
