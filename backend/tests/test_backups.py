import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.backup.destination import LocalDestination
from app.backup.format import MANIFEST, TIMELINE, BackupError, Manifest, json_bytes
from app.backup.service import BackupService
from app.core.config import PROJECT_ROOT, settings
from app.core.db import get_session
from app.editing.persistence import ProjectRecord
from app.main import app


@pytest.fixture
def studio(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(settings, "workspace_dir", workspace)
    monkeypatch.setattr(settings, "backup_dir", None)
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def session():
        with Session(engine) as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_session, session)
    client = TestClient(app)
    destination = tmp_path / "backups"
    response = client.put("/api/backups/settings", json={"folder": str(destination)})
    assert response.status_code == 200, response.text
    project = client.post("/api/projects", json={"name": "Prueba con clips"}).json()
    (workspace / "clip.mp4").write_bytes(b"media-fixture")
    project.update(assets=[{"id": "media", "name": "Clip", "path": "clip.mp4"}], tracks=[
        {"kind": "video", "id": "video", "name": "Vídeo", "clips": [
            {"id": "clip-a", "asset_id": "media", "duration_seconds": 1}]},
        {"kind": "subtitle", "id": "subs", "name": "Subtítulos", "cues": [
            {"id": "cue", "text": "Subtítulo de prueba", "duration_seconds": 1}]},
    ])
    response = client.put(f"/api/projects/{project['id']}", json=project)
    assert response.status_code == 200, response.text
    yield client, destination, workspace, project["id"], engine
    client.close()
    engine.dispose()


def preview(client, project_id, **extra):
    response = client.post("/api/backups/preview", json={"project_id": project_id, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def create(client, project_id, **extra):
    plan = preview(client, project_id, **extra)
    response = client.post("/api/backups", json={"project_id": project_id, **extra,
                           "confirmed": True, "revision": plan["revision"]})
    assert response.status_code == 201, response.text
    return response.json(), plan


def rewrite_timeline(folder, payload, manifest):
    data = json_bytes(payload)
    (folder / TIMELINE).write_bytes(data)
    entry = next(entry for entry in manifest["files"] if entry["name"] == TIMELINE)
    entry.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    (folder / MANIFEST).write_bytes(json_bytes(manifest))


def test_existing_project_json_and_v1_backup_without_notes(studio):
    client, root, _, project_id, engine = studio
    with Session(engine) as session:
        record = session.get(ProjectRecord, project_id)
        old = dict(record.payload)
        old["assets"] = [{k: v for k, v in asset.items() if k != "note"} for asset in old["assets"]]
        record.payload = old
        session.commit()

    project = client.get(f"/api/projects/{project_id}").json()
    assert project["assets"][0]["note"] is None
    with Session(engine) as session:
        assert "note" not in session.get(ProjectRecord, project_id).payload["assets"][0]

    created, _ = create(client, project_id, include_assets=True)
    folder = root / created["id"]
    manifest = json.loads((folder / MANIFEST).read_bytes())
    manifest["schema_version"] = 1
    manifest.pop("asset_notes")
    rewrite_timeline(folder, old, manifest)
    route = f"/api/backups/{folder.name}"
    assert client.post(route + "/verify").status_code == 200
    restored = client.post(route + "/restore")
    assert restored.status_code == 201
    assert client.get(f"/api/projects/{restored.json()['id']}").json()["assets"][0]["note"] is None


def test_v2_round_trip_preserves_note_manifest_hash_and_media(studio):
    client, root, _, project_id, _ = studio
    note = "Entrevista 🎧\nUsar solo los primeros 2 min."
    url = f"/api/projects/{project_id}/assets/media/note"
    assert client.put(url, json={"note": f" {note}\u202e "}).json()["note"] == note
    created, _ = create(client, project_id, include_assets=True)
    folder = root / created["id"]
    manifest = json.loads((folder / MANIFEST).read_bytes())
    assert manifest["asset_notes"] == {"media": note}
    for item in manifest["files"]:
        data = (folder / item["name"]).read_bytes()
        assert len(data) == item["size"] and hashlib.sha256(data).hexdigest() == item["sha256"]
    route = f"/api/backups/{folder.name}"
    assert client.post(route + "/verify").json()["verification"] == "verified"
    restored = client.post(route + "/restore")
    assert restored.status_code == 201
    asset = client.get(f"/api/projects/{restored.json()['id']}").json()["assets"][0]
    assert asset["note"] == note
    assert Path(asset["path"]).read_bytes() == b"media-fixture"
    assert "Entrevista" not in json.dumps(client.get("/api/backups/audit").json(), ensure_ascii=False)


@pytest.mark.parametrize("bad", ["x" * 501, "texto\u202e", " nota", "nota cambiada"])
def test_v2_rejects_invalid_or_mismatched_notes(studio, bad):
    client, root, _, project_id, _ = studio
    client.put(f"/api/projects/{project_id}/assets/media/note", json={"note": "Nota original"})
    created, _ = create(client, project_id)
    folder = root / created["id"]
    manifest = json.loads((folder / MANIFEST).read_bytes())
    manifest["asset_notes"]["media"] = bad
    (folder / MANIFEST).write_bytes(json_bytes(manifest))
    route = f"/api/backups/{folder.name}"
    for operation in ("verify", "restore"):
        response = client.post(f"{route}/{operation}")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "BACKUP_INVALID"
    assert client.get("/api/projects").json()["total"] == 1


def test_v2_rejects_unsanitized_timeline_even_with_recomputed_hash(studio):
    client, root, _, project_id, _ = studio
    client.put(f"/api/projects/{project_id}/assets/media/note", json={"note": "Nota original"})
    created, _ = create(client, project_id)
    folder = root / created["id"]
    manifest = json.loads((folder / MANIFEST).read_bytes())
    timeline = json.loads((folder / TIMELINE).read_bytes())
    timeline["assets"][0]["note"] += "\u0000"
    rewrite_timeline(folder, timeline, manifest)
    response = client.post(f"/api/backups/{folder.name}/restore")
    assert response.status_code == 422 and "no saneada" in response.json()["error"]["message"]


def test_manifest_hashes_metadata_and_exact_timeline_copy(studio):
    client, root, _, project_id, engine = studio
    from app.editing.drafts import DraftResult
    from app.editing.jobs import RenderJob

    with Session(engine) as session:
        session.add(DraftResult(id="draft", project_id=project_id, path="draft-path", plugin_id="capcut"))
        session.add(RenderJob(id="job", project_id=project_id, kind="final", status="done",
                              output_path="render.mp4", log="must not be included"))
        session.commit()
    created, plan = create(client, project_id)
    folder = root / created["id"]
    manifest = json.loads((folder / MANIFEST).read_bytes())
    assert manifest["schema_version"] == 2 and manifest["project_id"] == project_id
    assert manifest["project_name"] == "Prueba con clips" and manifest["created_at"].endswith("Z")
    assert {entry.name for entry in folder.iterdir()} == {MANIFEST, TIMELINE, "metadata.json"}
    assert sum(entry.stat().st_size for entry in folder.iterdir()) == plan["total_bytes"]
    for entry in manifest["files"]:
        contents = (folder / entry["name"]).read_bytes()
        assert entry["size"] == len(contents)
        assert entry["sha256"] == hashlib.sha256(contents).hexdigest()
    meta = json.loads((folder / "metadata.json").read_bytes())
    assert meta["jobs"][0]["status"] == "done" and meta["jobs"][0]["output_path"] == "render.mp4"
    assert "log" not in meta["jobs"][0] and meta["drafts"][0]["id"] == "draft"
    listed = client.get("/api/backups").json()["items"]
    assert listed[0]["verification"] == "unchecked"
    assert client.post(f"/api/backups/{created['id']}/verify").json()["verification"] == "verified"
    original = client.get(f"/api/projects/{project_id}").json()
    restored = client.post(f"/api/backups/{created['id']}/restore")
    assert restored.status_code == 201, restored.text
    copy_id = restored.json()["id"]
    assert copy_id != project_id and client.get(f"/api/projects/{project_id}").json() == original
    assert client.get(f"/api/projects/{copy_id}/timeline").content == client.get(f"/api/projects/{project_id}/timeline").content
    assert client.get(f"/api/jobs?project_id={copy_id}").json()["items"] == []


def test_assets_require_confirmation_and_restore_to_workspace(studio):
    client, root, workspace, project_id, _ = studio
    plan = preview(client, project_id, include_assets=True)
    payload = {"project_id": project_id, "include_assets": True, "revision": plan["revision"]}
    response = client.post("/api/backups", json=payload)
    assert response.status_code == 409 and not list(root.iterdir())
    (workspace / "clip.mp4").write_bytes(b"media-fixturf")
    assert client.post("/api/backups", json={**payload, "confirmed": True}).json()["error"]["code"] == "BACKUP_STALE_PREVIEW"
    created, plan = create(client, project_id, include_assets=True)
    assert any(entry["label"] == "clip.mp4" for entry in plan["files"])
    (workspace / "clip.mp4").unlink()
    restored = client.post(f"/api/backups/{created['id']}/restore")
    assert restored.status_code == 201, restored.text
    project = client.get(f"/api/projects/{restored.json()['id']}").json()
    asset = project["assets"][0]
    assert asset["id"] == "media" and Path(asset["path"]).is_relative_to(workspace)
    assert Path(asset["path"]).read_bytes() == b"media-fixturf"


@pytest.mark.parametrize("recompute", [False, True])
def test_corruption_and_invalid_timeline_never_import(studio, recompute):
    client, root, _, project_id, _ = studio
    created, _ = create(client, project_id)
    folder = root / created["id"]
    path = folder / TIMELINE
    contents = path.read_bytes()
    if not recompute:
        path.write_bytes(bytes([contents[0] ^ 1]) + contents[1:])
    else:
        invalid = json.loads(contents)
        invalid["tracks"][0]["clips"][0]["asset_id"] = "missing"
        data = json.dumps(invalid).encode()
        path.write_bytes(data)
        manifest = json.loads((folder / MANIFEST).read_bytes())
        entry = next(item for item in manifest["files"] if item["name"] == TIMELINE)
        entry.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        (folder / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    response = client.post(f"/api/backups/{created['id']}/restore")
    assert response.status_code == 422 and TIMELINE in response.json()["error"]["message"]
    assert client.get("/api/projects").json()["total"] == 1
    event = client.get("/api/backups/audit").json()[0]
    assert event["status"] == "denied" and event["action"] == "restaurar"
    assert "Subtítulo" not in json.dumps(event, ensure_ascii=False)


def test_paths_and_no_overwrite(studio):
    client, root, workspace, project_id, engine = studio
    system = Path(os.environ["SystemRoot"]) if os.name == "nt" else Path("/usr")
    for path in ("relative", str(root / ".." / "other"), str(PROJECT_ROOT / "invalid"),
                 str(workspace / "loop"), str(system / "invalid")):
        assert client.put("/api/backups/settings", json={"folder": path}).status_code == 422
    with Session(engine) as session:
        destination = LocalDestination(root)
        plan = BackupService(session, destination).plan(project_id, False)
        destination.save(plan.manifest, plan.sources)
        before = (root / plan.manifest.id / TIMELINE).read_bytes()
        with pytest.raises(BackupError, match="no se sobrescribió"):
            destination.save(plan.manifest, {**plan.sources, TIMELINE: b"changed"})
        assert (root / plan.manifest.id / TIMELINE).read_bytes() == before
        with pytest.raises(BackupError):
            destination.read(plan.manifest.id, "../timeline.json")
        with pytest.raises(BackupError):
            destination.read("../outside", TIMELINE)
    project = client.get(f"/api/projects/{project_id}").json()
    project["assets"][0]["path"] = str(root / "outside.mp4")
    assert client.put(f"/api/projects/{project_id}", json=project).status_code == 200
    result = client.post("/api/backups/preview", json={"project_id": project_id, "include_assets": True})
    assert result.status_code == 422 and "GHS_WORKSPACE_DIR" in result.text


def test_linked_member_and_escaping_manifest_are_rejected(studio):
    client, root, _, project_id, _ = studio
    created, _ = create(client, project_id)
    folder = root / created["id"]
    original = folder / TIMELINE
    outside = root.parent / "outside.json"
    original.rename(outside)
    os.link(outside, original)
    assert client.post(f"/api/backups/{created['id']}/restore").status_code == 422
    manifest = Manifest.model_validate_json((folder / MANIFEST).read_bytes()).model_dump(mode="json")
    manifest["files"][0]["name"] = "../outside.json"
    (folder / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert client.get("/api/backups").json()["items"][0]["verification"] == "invalid"


def test_directory_link_cannot_redirect_destination_or_backup(studio):
    client, root, workspace, project_id, _ = studio
    created, _ = create(client, project_id)
    folder = root / created["id"]
    outside = workspace / "relocated"
    folder.rename(outside)

    def link(target, name):
        if os.name == "nt":
            from _winapi import CreateJunction

            CreateJunction(str(target), str(name))
        else:
            name.symlink_to(target, target_is_directory=True)

    link(outside, folder)
    link(workspace, root.parent / "linked-destination")
    result = client.put("/api/backups/settings", json={"folder": str(root.parent / "linked-destination")})
    assert result.status_code == 422
    assert client.post(f"/api/backups/{created['id']}/restore").status_code == 422
    assert client.get("/api/backups").json()["items"][0]["verification"] == "invalid"


def test_size_and_disk_space_checks(studio, monkeypatch):
    client, root, _, project_id, _ = studio
    with monkeypatch.context() as patch:
        patch.setattr(settings, "backup_max_bytes", 10)
        result = client.post("/api/backups/preview", json={"project_id": project_id})
        assert result.json()["error"]["code"] == "BACKUP_SIZE_LIMIT"
    plan = preview(client, project_id)
    usage = shutil.disk_usage(root)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage._replace(free=1))
    result = client.post("/api/backups", json={"project_id": project_id, "revision": plan["revision"], "confirmed": True})
    assert result.json()["error"]["code"] == "BACKUP_NO_SPACE"
    assert not list(root.iterdir())
