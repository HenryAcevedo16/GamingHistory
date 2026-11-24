import errno
import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.routes import renders, uploads
from app.core import db as database
from app.core.config import settings
from app.core.db import get_session
from app.editing.adapters import ffmpeg
from app.main import app
from app.models.audit import AuditLog
from app.models.plugin import PluginState

HEADER = {"X-GHS-Upload": "1"}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_dir", workspace)
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(PluginState(plugin_id="ffmpeg", enabled=True, connected=True))
        db.commit()

    def session():
        with Session(engine) as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_session, session)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(ffmpeg, "engine", engine)
    monkeypatch.setattr(renders, "engine", engine)
    # The route uses the actual adapter, which is automatically registered on import.
    with TestClient(app, base_url="http://localhost") as client:
        project = client.post("/api/projects", json={"name": "Subidas de prueba"}).json()
        yield client, f"/api/projects/{project['id']}", workspace, engine
    engine.dispose()


@pytest.fixture
def wav():
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe no está disponible")
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        handle.writeframes(bytes(16000))
    return output.getvalue()


def upload(client, route, *parts):
    response = client.post(route + "/assets/upload", headers=HEADER, files=parts)
    assert response.status_code == 200, response.text
    return response.json()


def assets(client, route):
    return client.get(route).json()["assets"]


@pytest.mark.parametrize("name", ["../escape.mp4", r"C:\outside\clip.mp4", r"\\server\share\clip.mp4",
                                  "CON.mp4", "AUX .wav", "LPT¹.wav", "hide\u202e.wav", "x\x00.wav"])
def test_unsafe_names_leave_no_files(studio, name):
    client, route, workspace, _ = studio
    result, = upload(client, route, ("files", (name, b"bad")))
    assert not result["ok"] and result["error"]["code"] == "UPLOAD_BAD_NAME"
    assert not list(workspace.iterdir()) and not assets(client, route)


def test_allowlist_and_large_limit(studio, monkeypatch):
    client, route, workspace, _ = studio
    monkeypatch.setattr(settings, "upload_max_bytes", 65536)
    a, b = upload(client, route, ("files", ("fake.exe", b"x")), ("files", ("large.wav", bytes(65537))))
    assert [r["error"]["code"] for r in (a, b)] == ["UPLOAD_FORMAT", "UPLOAD_TOO_LARGE"]
    assert not list(workspace.iterdir()) and not assets(client, route)


def test_requires_local_upload_header(studio):
    client, route, _, _ = studio
    url = route + "/assets/upload"
    assert client.post(url).status_code == 403
    assert client.post(url, headers={**HEADER, "Host": "external.example"}).status_code == 403
    assert client.post(url, headers={**HEADER, "Origin": "https://external.example"}).status_code == 403


def test_multi_with_real_probe_duplicate_and_note(studio, wav):
    client, route, workspace, engine = studio
    a, b, c = upload(client, route, ("files", ("voz.wav", wav)),
                     ("note", (None, "  Entrevista\u0000; usar 2 min  ")), ("files", ("bad.wav", b"not audio")),
                     ("files", ("voz.wav", wav)))
    assert a["ok"] and a["asset"]["note"] == "Entrevista; usar 2 min"
    assert b["error"]["code"] == "MEDIA_PROBE_FAILED" and "ffprobe" in b["error"]["message"]
    assert c["ok"] and c["asset"]["note"] is None
    assert {a["asset"]["name"], c["asset"]["name"]} == {"voz.wav", "voz-1.wav"}
    saved = assets(client, route)
    assert saved == [a["asset"], c["asset"]]
    assert all(asset["duration_seconds"] == 1 and asset["kind"] == "audio" for asset in saved)
    assert sorted(p.name for p in workspace.rglob("*.wav")) == ["voz-1.wav", "voz.wav"]
    assert all(Path(asset["path"]).read_bytes() == wav for asset in saved)
    updated = client.put(f"{route}/assets/{saved[0]['id']}/note", json={"note": " editada\u202e "})
    assert updated.json()["note"] == "editada"
    assert client.put(f"{route}/assets/{saved[0]['id']}/note", json={"note": "x" * 501}).status_code == 422
    assert assets(client, route)[0]["note"] == "editada"
    with Session(engine) as db:
        rows = db.exec(select(AuditLog)).all()
        assert [row.status for row in rows] == ["ok", "ok", "error"]
        assert all("Entrevista" not in row.detail and "editada" not in row.detail for row in rows)


def test_wrong_content_and_long_note_leave_no_copies(studio, wav):
    client, route, workspace, _ = studio
    a, b = upload(client, route, ("files", ("wrong.mp4", wav)),
                  ("files", ("valid.wav", wav)), ("note", (None, "ñ" * 501)))
    assert [r["error"]["code"] for r in (a, b)] == ["MEDIA_PROBE_FAILED", "UPLOAD_BAD_NOTE"]
    assert not list(workspace.iterdir()) and not assets(client, route)


def test_disconnect_after_partial_write(studio):
    client, route, workspace, _ = studio
    opened = []

    async def request():
        messages = iter([
            {"type": "http.request", "body": b'--side\r\nContent-Disposition: form-data; name="files"; filename="partial.wav"\r\n\r\n'
             + bytes(128 * 1024), "more_body": True},
            {"type": "http.disconnect"},
        ])

        async def receive():
            message = next(messages)
            if message["type"] == "http.disconnect":
                opened.extend(path.stat().st_size for path in workspace.rglob("*.wav"))
            return message

        async def send(_):
            pass

        await app({"type": "http", "asgi": {"version": "3.0"}, "method": "POST",
                   "path": route + "/assets/upload", "headers": [(b"content-type", b"multipart/form-data; boundary=side"),
                                                                (b"x-ghs-upload", b"1")],
                   "query_string": b"", "scheme": "http", "server": ("localhost", 80)}, receive, send)

    anyio.run(request)
    assert opened and opened[0] > 0
    assert not list(workspace.iterdir()) and not assets(client, route)


def test_partial_disk_write_and_save_failure_clean_up(studio, wav, monkeypatch):
    client, route, workspace, _ = studio
    real_open = Path.open

    class FullDisk:
        def __init__(self, file):
            self.file = file

        def write(self, data):
            self.file.write(data[:5])
            raise OSError(errno.ENOSPC, "disk full")

        def close(self):
            self.file.close()

    def open_file(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        return FullDisk(handle) if path.name == "full.wav" and mode == "xb" else handle

    monkeypatch.setattr(Path, "open", open_file)
    a, b = upload(client, route, ("files", ("full.wav", wav)), ("files", ("ok.wav", wav)))
    assert a["error"]["code"] == "UPLOAD_DISK_FULL" and b["ok"]
    assert not list(workspace.rglob("full.wav"))
    before = set(workspace.iterdir())

    def fail(*args, **kwargs):
        raise OperationalError("INSERT", {}, RuntimeError("unavailable"))

    monkeypatch.setattr(uploads, "commit_imports", fail)
    response = client.post(route + "/assets/upload", headers=HEADER, files=[("files", ("db-failed.wav", wav))])
    assert response.status_code == 500 and response.json()["error"]["code"] == "UPLOAD_SAVE_FAILED"
    assert len(assets(client, route)) == 1 and set(workspace.iterdir()) == before


def test_independent_uploads_never_reuse_a_filename_in_the_project(studio, wav):
    client, route, _, _ = studio
    a, = upload(client, route, ("files", ("voz.wav", wav)))
    b, = upload(client, route, ("files", ("VOZ.wav", wav)))
    assert a["asset"]["name"] == "voz.wav" and b["asset"]["name"] == "VOZ-1.wav"
    assert a["asset"]["path"] != b["asset"]["path"]
    assert Path(a["asset"]["path"]).read_bytes() == Path(b["asset"]["path"]).read_bytes() == wav


def test_path_import_reuses_probe_and_still_rejects_external_files(studio, wav, tmp_path):
    client, route, workspace, _ = studio
    workspace.mkdir()
    inside = workspace / "local.wav"
    outside = tmp_path / "external.wav"
    for path in (inside, outside):
        path.write_bytes(wav)
    assert client.post(route + "/media", json={"path": str(outside)}).status_code == 422
    response = client.post(route + "/media", json={"path": inside.name, "note": " Audio de referencia "})
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    assert asset["note"] == "Audio de referencia" and Path(asset["path"]) == inside
    assert list(workspace.iterdir()) == [inside] and inside.read_bytes() == outside.read_bytes() == wav


def test_locked_tracks_are_protected_when_validating_and_saving(studio, wav):
    client, route, _, _ = studio
    recorded, = upload(client, route, ("files", ("vous.wav", wav)))
    project = client.get(route).json()
    locked = {"kind": "audio", "id": "locked", "name": "No editar", "locked": True, "clips": []}
    project["tracks"] = [locked]
    assert client.put(route, json=project).status_code == 200
    candidate = {"tracks": [{**locked, "clips": [{"asset_id": recorded["asset"]["id"], "duration_seconds": 1}]}]}
    for response in (client.post(route + "/timeline/validate", json=candidate),
                     client.put(route + "/timeline", json=candidate)):
        assert response.status_code == 422 and response.json()["error"]["code"] == "TRACK_LOCKED"
    assert client.get(route + "/timeline").json()["tracks"][0]["clips"] == []


def test_still_uploaded_and_rendered_with_real_ffmpeg(studio, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe no disponibles")
    client, route, workspace, _ = studio
    source = tmp_path / "still.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=blue:s=160x90",
                    "-frames:v", "1", "-update", "1", str(source)], check=True)
    result, = upload(client, route, ("files", ("still.png", source.read_bytes())))
    assert result["ok"] and result["asset"]["kind"] == "image", result
    candidate = {"tracks": [{"kind": "video", "name": "Foto", "clips": [
        {"asset_id": result["asset"]["id"], "duration_seconds": 1}
    ]}]}
    assert client.put(route + "/timeline", json=candidate).status_code == 200
    output = workspace / "still.mp4"
    response = client.post(route + "/renders/final", json={"output_path": str(output)})
    assert response.status_code == 202
    status = client.get("/api/jobs/" + response.json()["id"]).json()
    assert status["status"] == "done", status
    media = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                               "format=duration", "-of", "json", str(output)]))
    assert float(media["format"]["duration"]) == 1
