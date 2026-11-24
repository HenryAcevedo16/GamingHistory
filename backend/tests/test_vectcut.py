import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.core import db
from app.core.config import settings
from app.core.errors import CapabilityNotAvailable, InvalidOperation
from app.core.exec import run_command
from app.editing.adapters.vectcut import VectCutAdapter, VectCutConverter, VectCutUnavailable
from app.editing.persistence import ProjectRepository
from app.editing.timeline import Asset, AudioClip, AudioTrack, Clip, Effect, Project, SubtitleCue, SubtitleTrack, VideoTrack
from app.main import app
from app.models.audit import AuditLog

PLUGIN = "vectcut-capcut"
PLUGIN_URL = f"/api/plugins/{PLUGIN}"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{tmp_path / 'test.db'}"))
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspace")
    db.init_db()
    return settings.resolved_workspace_dir


@pytest.fixture
def vectcut_http(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    (root / "settings").mkdir(parents=True)
    (root / "capcut_server.py").touch()
    (root / "settings" / "local.py").touch()
    calls = []
    draft_id = "dfd_cat_1234567890_abcdef00"
    text = "GHS subtitle"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.command, self.path, {}))
            self.reply([{"name": "思源粗宋"}])

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.command, self.path, payload))
            if self.path == "/save_draft":
                assert payload["auto_deploy"] is False and payload["auto_reload"] is False
                assert "project_name" not in payload
                path = Path(payload["draft_folder"]) / draft_id
                path.mkdir()
                content = {"canvas_config": {"width": 320, "height": 240},
                           "tracks": [{"type": "text", "name": "ghs_subtitle_1", "segments": [
                               {"material_id": "mat", "target_timerange": {"start": 200000, "duration": 650000}}
                           ]}], "materials": {"texts": [{"id": "mat", "content": json.dumps({"text": text})}]}}
                (path / "draft_info.json").write_text(json.dumps(content), encoding="utf-8")
                (path / "draft_meta_info.json").write_text('{"cloud_draft_sync":true}', encoding="utf-8")
                self.reply({"success": True, "draft_url": str(path)})
            else:
                self.reply({"draft_id": draft_id, "draft_url": "https://unused.invalid/"})

        def reply(self, output):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "output": output}).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        monkeypatch.setenv("VECTCUT_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("VECTCUT_ROOT", str(root))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield calls
        finally:
            server.shutdown()
            worker.join()


def sample_project(video=None, audio=None):
    project = Project(name="VectCut smoke")
    if video:
        project.assets.append(Asset(id="video", name="bars", path=str(video), duration_seconds=2))
        project.tracks.append(VideoTrack(name="Video", clips=[
            Clip(id="clip", asset_id="video", source_in_seconds=.25, duration_seconds=1),
        ]))
    if audio:
        project.assets.append(Asset(id="audio", name="tone", kind="audio", path=str(audio), duration_seconds=2))
        project.tracks.append(AudioTrack(name="Audio", clips=[
            AudioClip(id="audio-clip", asset_id="audio", start_seconds=.25, duration_seconds=1, gain_db=-6),
        ]))
    project.tracks.append(SubtitleTrack(name="Subs", cues=[
        SubtitleCue(id="cue", start_seconds=.2, duration_seconds=.65, text="GHS subtitle"),
    ]))
    return project


def install_connect(api):
    installed = api.post(f"{PLUGIN_URL}/install", json={"confirm_permissions": True})
    assert installed.status_code == 200, installed.text
    connected = api.post(f"{PLUGIN_URL}/connect")
    assert connected.status_code == 200, connected.text
    assert connected.json()["plugin"]["connected"]


def test_http_contract_and_explicit_deploy(sandbox, vectcut_http, monkeypatch):
    if not run_command("ffmpeg", ["-version"]).ok:
        pytest.skip("Plugin Manager comprueba que FFmpeg está instalado")
    deploy = sandbox.parent / "capcut-drafts"
    deploy.mkdir()
    monkeypatch.setenv("CAPCUT_DRAFTS_DIR", str(deploy))
    with TestClient(app) as api:
        install_connect(api)
        assert not api.get(PLUGIN_URL).json()["verified_capabilities"]
        assert not VectCutAdapter(PLUGIN).get_capabilities().verified
        assert api.post("/api/router/decide", json={"operation": "editable_draft"}).json()["selected"] is None
        project = sample_project()
        with Session(db.engine) as session:
            ProjectRepository(session).save(project)
        url = f"/api/projects/{project.id}/drafts"
        created = api.post(url, json={"width": 320, "height": 240})
        assert created.status_code == 201, created.text
        draft = created.json()["draft"]
        assert api.get(url).json() == [draft]
        assert VectCutAdapter(PLUGIN).get_capabilities().verified
        assert set(api.get(PLUGIN_URL).json()["verified_capabilities"]) == {
            "draft.create", "draft.save", "draft.export_capcut", "subtitle.add",
        }
        assert api.post("/api/router/decide", json={"operation": "editable_draft"}).json()["selected"] is None
        copy_url = f"{url}/{draft['id']}/deploy"
        assert not list(deploy.iterdir())
        assert api.post(copy_url, json={"confirm_copy": False}).status_code == 422
        assert not list(deploy.iterdir())
        assert api.post(copy_url, json={"confirm_copy": True}).status_code == 201
        assert (deploy / draft["id"] / "draft_info.json").is_file()
        metadata = json.loads((deploy / draft["id"] / "draft_meta_info.json").read_text(encoding="utf-8"))
        assert metadata["cloud_draft_sync"] is False
        assert Path(metadata["draft_fold_path"]) == deploy / draft["id"]
        assert api.post(copy_url, json={"confirm_copy": True}).status_code == 409
    assert [path for method, path, _ in vectcut_http if method == "POST"] == [
        "/create_draft", "/add_subtitle", "/save_draft",
    ]
    assert vectcut_http[-2][2]["srt"] == "1\n00:00:00,200 --> 00:00:00,850\nGHS subtitle\n"


@pytest.mark.parametrize("endpoint", ["https://example.test:9000", "http://192.168.1.9:9000", "http://localhost:9000/api"])
def test_reject_endpoint_without_logging_value(sandbox, monkeypatch, endpoint):
    monkeypatch.setenv("VECTCUT_ENDPOINT", endpoint)
    adapter = VectCutAdapter(PLUGIN)
    assert not adapter.health_check()
    with Session(db.engine) as session:
        row = session.exec(select(AuditLog)).one()
        assert (row.status, row.detail) == ("denied", "invalid_endpoint")
        assert endpoint not in row.model_dump_json()


def test_reject_media_and_operations_before_http(sandbox, vectcut_http):
    project = sample_project("../outside.mp4")
    with Session(db.engine) as session:
        ProjectRepository(session).save(project)
    adapter = VectCutAdapter(PLUGIN)
    with pytest.raises(InvalidOperation):
        adapter.export_project(project.id, "capcut")
    with pytest.raises(CapabilityNotAvailable):
        adapter.render_final(project.id)
    with pytest.raises(CapabilityNotAvailable):
        adapter._call("POST", "/secret-unknown-path")
    assert not vectcut_http
    with Session(db.engine) as session:
        rows = session.exec(select(AuditLog)).all()
        assert any(row.detail == "endpoint_not_allowed" and row.status == "denied" for row in rows)
        assert all("secret-unknown-path" not in row.model_dump_json() for row in rows)


def test_converter_reports_unsupported_and_preserves_positions():
    project = sample_project("clip.mp4", "tone.mp3")
    project.tracks[0].clips[0].effects = [Effect(id="fx", name="blur")]
    project.tracks[1].clips[0].fade_in_seconds = .2
    plan = VectCutConverter().convert(project)
    assert plan.supported and not plan.complete
    assert {entry.kind for entry in plan.unsupported} == {"effect", "audio_fade"}
    video, audio, cue = plan.payload["items"]
    assert (video["source"], video["start"], video["length"]) == (250000, 0, 1000000)
    assert (audio["start"], audio["volume"]) == (250000, pytest.approx(.501187))
    assert (cue["start"], cue["length"], cue["text"]) == (200000, 650000, "GHS subtitle")


@pytest.mark.skipif(os.environ.get("GHS_VECTCUT_LIVE") != "1", reason="activa GHS_VECTCUT_LIVE=1 para generar un borrador real")
def test_vectcut_real_http_and_draft_on_disk(sandbox):
    adapter = VectCutAdapter(PLUGIN)
    try:
        adapter._call("GET", "/get_font_types")
    except VectCutUnavailable:
        pytest.skip("VectCutAPI no responde por HTTP en VECTCUT_ENDPOINT (loopback)")
    assert adapter.health_check(), adapter.last_health_error if hasattr(adapter, "last_health_error") else ""
    video, audio = sandbox / "bars.mp4", sandbox / "tone.mp3"
    for source, codec, path in [("testsrc2=size=320x240:rate=24", "libx264", video),
                                ("sine=frequency=440", "libmp3lame", audio)]:
        kind = "v" if path == video else "a"
        result = run_command("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", source, "-t", "2",
                                        f"-c:{kind}", codec, str(path)], timeout=30)
        assert result.ok, result.output
    project = sample_project(video, audio)
    with Session(db.engine) as session:
        ProjectRepository(session).save(project)
    with TestClient(app) as api:
        install_connect(api)
        url = f"/api/projects/{project.id}/drafts"
        created = api.post(url, json={"width": 320, "height": 240})
        assert created.status_code == 201, created.text
        assert created.json()["unsupported"] == []
        draft = created.json()["draft"]
        assert api.get(url).json() == [draft]
        info = Path(draft["path"]) / "draft_info.json"
        data = json.loads(info.read_text(encoding="utf-8"))
        tracks = {track["name"]: track["segments"][0] for track in data["tracks"] if track["segments"]}
        assert tracks["ghs_video_1"]["source_timerange"] == {"start": 250000, "duration": 1000000}
        assert tracks["ghs_audio_2"]["target_timerange"] == {"start": 250000, "duration": 1000000}
        assert tracks["ghs_subtitle_3"]["target_timerange"] == {"start": 200000, "duration": 650000}
        assert json.loads(data["materials"]["texts"][0]["content"])["text"] == "GHS subtitle"
        assert Path(data["materials"]["videos"][0]["path"]).is_file()
        assert Path(data["materials"]["audios"][0]["path"]).is_file()
        assert tracks["ghs_audio_2"]["volume"] == pytest.approx(.501187)
        meta = json.loads(info.with_name("draft_meta_info.json").read_text(encoding="utf-8"))
        assert meta["cloud_draft_sync"] is False and meta["cloud_draft_cover"] is False
        selected = api.post("/api/router/decide", json={"operation": "editable_draft"}).json()["selected"]
        assert selected["plugin_id"] == PLUGIN and selected["executable"]
        print(f"Borrador real: {info}; MP4, MP3 y subtítulo verificados en disco")
