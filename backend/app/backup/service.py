from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session

from app.backup.destination import BackupDestination, cleanup
from app.backup.format import (
    JSON_LIMIT, MANIFEST, METADATA, TIMELINE, BackupError, BackupFile, Manifest,
    check_file, json_bytes, measure, sha256,
)
from app.backup.paths import disk_space, read_file, without_links, workspace_file
from app.core.config import settings
from app.editing.drafts import list_drafts
from app.editing.jobs import JobRepository
from app.editing.persistence import ProjectRecord, ProjectRepository
from app.editing.timeline import Project, new_id


@dataclass
class Plan:
    manifest: Manifest
    sources: dict[str, bytes | Path]
    preview: dict


class BackupService:
    def __init__(self, session: Session, destination: BackupDestination):
        self.session = session
        self.destination = destination

    def plan(self, project_id: str, include_assets: bool) -> Plan:
        project = ProjectRepository(self.session).get(project_id)
        drafts = [draft.model_dump(mode="json") for draft in list_drafts(self.session, project_id)]
        fields = {"id", "project_id", "plugin_id", "kind", "status", "progress",
                  "output_path", "created_at", "started_at", "completed_at"}
        jobs = [job.model_dump(mode="json", include=fields)
                for job in JobRepository(self.session).list(project_id)]
        sources: dict[str, bytes | Path] = {
            TIMELINE: json_bytes(project.model_dump(mode="json")),
            METADATA: json_bytes({"drafts": drafts, "jobs": jobs}),
        }
        files: list[BackupFile] = []
        total = 0
        for name, data in sources.items():
            assert isinstance(data, bytes)
            if len(data) > JSON_LIMIT:
                raise BackupError(f"{name} supera el límite JSON.", code="BACKUP_SIZE_LIMIT")
            files.append(BackupFile(name=name, size=len(data), sha256=sha256(data)))
            total += len(data)
        if total > settings.backup_max_bytes:
            raise BackupError("El respaldo supera el límite configurado.", code="BACKUP_SIZE_LIMIT")

        labels = {name: name for name in sources}
        if include_assets:
            assets = [asset for asset in project.assets if asset.path is not None]
            if len(assets) > 1000:
                raise BackupError("El respaldo admite hasta 1000 archivos de recursos.")
            for index, asset in enumerate(assets, 1):
                try:
                    path = workspace_file(asset.path or "")
                    with read_file(path, single_link=True) as source:
                        size, digest = measure(source, settings.backup_max_bytes - total)
                except OSError:
                    raise BackupError(f"No se puede leer el recurso #{index} del workspace.") from None
                suffix = path.suffix.lower()
                name = f"asset-{index:04d}" + (suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else "")
                files.append(BackupFile(name=name, size=size, sha256=digest, asset_id=asset.id))
                sources[name] = path
                labels[name] = path.name
                total += size

        now = datetime.now(timezone.utc)
        if not now.microsecond:
            now = now.replace(microsecond=1)
        manifest = Manifest(schema_version=1, id=f"{now:%Y%m%dT%H%M%S%fZ}-{new_id()}", created_at=now,
                            project_id=project.id, project_name=project.name, files=files)
        manifest_size = len(manifest.model_dump_json().encode("utf-8"))
        if manifest_size > JSON_LIMIT or total + manifest_size > settings.backup_max_bytes:
            raise BackupError("El respaldo supera el límite configurado.", code="BACKUP_SIZE_LIMIT")
        state = self.destination.state(total + manifest_size)
        revision = sha256(json_bytes({
            "destination": state.location, "include_assets": include_assets,
            "snapshot": manifest.model_dump(mode="json", exclude={"id", "created_at"}),
        }))
        return Plan(manifest, sources, {
            "revision": revision, "location": state.location, "free_bytes": state.free_bytes,
            "total_bytes": total + manifest_size, "include_assets": include_assets,
            "files": [{"name": MANIFEST, "label": MANIFEST, "size": manifest_size}] + [
                {"name": f.name, "label": labels[f.name], "size": f.size} for f in files
            ],
        })

    def create(self, project_id: str, include_assets: bool, revision: str, confirmed: bool) -> dict:
        if not confirmed:
            raise BackupError("Confirma la vista previa para crear el respaldo.", status_code=409,
                              code="BACKUP_CONFIRMATION_REQUIRED")
        plan = self.plan(project_id, include_assets)
        if plan.preview["revision"] != revision:
            raise BackupError("Cambió el contenido o el destino. Genera otra vista previa.",
                              status_code=409, code="BACKUP_STALE_PREVIEW")
        self.destination.save(plan.manifest, plan.sources)
        return self.describe(plan.manifest, "verified", plan.preview["total_bytes"])

    def _manifest(self, backup_id: str) -> tuple[Manifest, int]:
        try:
            with self.destination.read(backup_id, MANIFEST) as source:
                data = source.read(JSON_LIMIT + 1)
            if len(data) > JSON_LIMIT:
                raise BackupError("El manifiesto supera el límite permitido.")
            manifest = Manifest.model_validate_json(data)
        except FileNotFoundError:
            raise BackupError("No se encontró manifest.json: respaldo inexistente o incompleto.",
                              status_code=404) from None
        except ValidationError:
            raise BackupError("manifest.json no cumple el esquema de respaldo.") from None
        if manifest.id != backup_id:
            raise BackupError("El ID del manifiesto no coincide con el respaldo.")
        size = len(data) + sum(f.size for f in manifest.files)
        if size > settings.backup_max_bytes:
            raise BackupError("El respaldo supera el límite configurado.", code="BACKUP_SIZE_LIMIT")
        return manifest, size

    @staticmethod
    def describe(manifest: Manifest, status: str, size: int) -> dict:
        return {"id": manifest.id, "project_id": manifest.project_id,
                "project_name": manifest.project_name, "created_at": manifest.created_at,
                "total_bytes": size, "verification": status,
                "assets": sum(f.asset_id is not None for f in manifest.files)}

    def list(self) -> list[dict]:
        items = []
        for backup_id in self.destination.list():
            try:
                manifest, size = self._manifest(backup_id)
                items.append(self.describe(manifest, "unchecked", size))
            except BackupError as exc:
                items.append({"id": backup_id, "verification": "invalid", "error": exc.message})
            except OSError:
                items.append({"id": backup_id, "verification": "invalid", "error": "Manifiesto ilegible."})
        return items

    def _check(self, backup_id: str, entry: BackupFile, output=None) -> None:
        try:
            with self.destination.read(backup_id, entry.name) as source:
                check_file(source, entry, output)
        except OSError:
            raise BackupError(f"No se pudo leer o copiar {entry.name}.") from None

    def verify(self, backup_id: str) -> dict:
        manifest, size = self._manifest(backup_id)
        for entry in manifest.files:
            self._check(backup_id, entry)
        return self.describe(manifest, "verified", size)

    def restore(self, backup_id: str) -> Project:
        manifest, _ = self._manifest(backup_id)
        files = {entry.name: entry for entry in manifest.files}
        with io.BytesIO() as data:
            self._check(backup_id, files[TIMELINE], data)
            try:
                original = Project.model_validate_json(data.getvalue())
            except ValidationError:
                raise BackupError("timeline.json no cumple el modelo de proyecto.") from None
        self._check(backup_id, files[METADATA])
        if (original.id, original.name) != (manifest.project_id, manifest.project_name):
            raise BackupError("El proyecto no coincide con el manifiesto.")
        assets = {entry.asset_id: entry for entry in manifest.files if entry.asset_id is not None}
        if not assets.keys() <= {asset.id for asset in original.assets}:
            raise BackupError("El manifiesto incluye recursos que no existen en el timeline.")

        now = datetime.now(timezone.utc)
        payload = original.model_dump()
        copy_id = new_id()
        payload.update(id=copy_id, name=f"{original.name} (copia)", created_at=now, updated_at=now)
        folder = workspace_file(f"restored-{copy_id}") if assets else None
        for asset in payload["assets"]:
            if asset["id"] in assets:
                asset["path"] = str(folder / assets[asset["id"]].name)
            elif asset["path"] is not None:
                workspace_file(asset["path"])
        copy = Project.model_validate(payload)
        owned: list[Path] = []
        if folder is not None:
            disk_space(folder.parent, sum(entry.size for entry in assets.values()) + 1)
            folder.mkdir(mode=0o700)
        try:
            if folder is not None:
                for entry in assets.values():
                    without_links(folder)
                    target = folder / entry.name
                    with target.open("xb") as output:
                        owned.append(target)
                        self._check(backup_id, entry, output)
            # INSERT, not the repository's upsert: even a collision cannot replace a project.
            self.session.add(ProjectRecord(id=copy.id, name=copy.name, created_at=now, updated_at=now,
                                           payload=copy.model_dump(mode="json")))
            self.session.commit()
            return copy
        except Exception:
            if folder is not None:
                cleanup(folder, owned)
            raise
