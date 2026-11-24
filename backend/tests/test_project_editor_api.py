from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.core import db
from app.core.config import settings
from app.editing.jobs import JobRepository
from app.main import app
import pytest


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{tmp_path / 'studio.db'}"))
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "media")
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Editor test"}).json()
        yield client, project, f"/api/projects/{project['id']}"


def test_validate_without_saving_checks_overlaps_durations_and_references(studio):
    client, project, route = studio
    project["assets"] = [{"id": "asset", "name": "source", "duration_seconds": 2}]
    assert client.put(route, json=project).status_code == 200
    first = {"id": "first", "asset_id": "asset", "start_seconds": 0, "duration_seconds": 1}
    tracks = [{"kind": "video", "name": "V1", "clips": [first]}]
    assert client.post(f"{route}/timeline/validate", json={"tracks": tracks}).status_code == 200
    for second, reason in [
        ({"start_seconds": 0.5}, "Solapamiento"),
        ({"start_seconds": 1, "asset_id": "missing"}, "inexistente"),
        ({"start_seconds": 1, "source_in_seconds": 2}, "que dura 2s"),
        ({"start_seconds": 1, "duration_seconds": 0}, "greater than 0"),
    ]:
        tracks[0]["clips"] = [first, {**first, "id": "second", **second}]
        response = client.post(f"{route}/timeline/validate", json={"tracks": tracks})
        assert response.status_code == 422 and reason in response.text
    assert client.get(f"{route}/timeline").json()["tracks"] == []


def test_preflight_reports_unsupported_without_running_and_resolve_is_gated(studio):
    client, _, route = studio
    payload = {"tracks": [{"kind": "subtitle", "name": "S1", "cues": [{"text": "Hola", "duration_seconds": 1}]}]}
    assert client.put(f"{route}/timeline", json=payload).status_code == 200
    assert client.get(f"{route}/exports/unknown/preflight").status_code == 422
    ffmpeg = client.get(f"{route}/exports/ffmpeg/preflight").json()
    assert not ffmpeg["available"] and ffmpeg["unsupported"][0]["kind"] == "subtitles"
    assert client.get("/api/jobs").json()["items"] == []
    resolve = client.get(f"{route}/exports/resolve/preflight").json()
    assert not resolve["available"] and resolve["unsupported"][0]["kind"] == "subtitles"
    assert client.post(f"{route}/exports/resolve", json={"revision": resolve["revision"]}).status_code == 409
    assert client.put(f"{route}/timeline", json={}).status_code == 200
    stale = client.post(f"{route}/exports/resolve", json={"revision": resolve["revision"]})
    assert stale.status_code == 409 and "cambió" in stale.json()["error"]["message"]
    stale = client.post(f"{route}/renders/final", json={"revision": ffmpeg["revision"], "output_path": "safe.mp4"})
    assert stale.status_code == 409 and client.get("/api/jobs").json()["items"] == []


def test_download_only_completed_workspace_result(studio, tmp_path):
    client, project, _ = studio
    media = settings.resolved_workspace_dir / "result.mp4"
    media.write_bytes(b"render result")
    outside = tmp_path / "outside.mp4"
    outside.touch()
    with Session(db.engine) as session:
        jobs = JobRepository(session)
        ready = jobs.create(project_id=project["id"], kind="final", output_path=str(media))
        waiting = jobs.create(project_id=project["id"], kind="final", output_path=str(media))
        unsafe = jobs.create(project_id=project["id"], kind="final", output_path=str(outside))
        jobs.update(ready, status="done")
        jobs.update(unsafe, status="done")
        ready_id, waiting_id, unsafe_id = ready.id, waiting.id, unsafe.id
    result = client.get(f"/api/jobs/{ready_id}/result")
    assert result.status_code == 200 and result.content == b"render result"
    assert result.headers["content-disposition"] == 'attachment; filename="result.mp4"'
    assert client.get(f"/api/jobs/{waiting_id}/result").status_code == 404
    assert client.get(f"/api/jobs/{unsafe_id}/result").status_code == 422
    media.unlink()
    assert client.get(f"/api/jobs/{ready_id}/result").status_code == 404
