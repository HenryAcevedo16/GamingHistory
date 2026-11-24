"""Shared inspection and persistence for path imports and uploaded copies."""

from pathlib import Path

from sqlmodel import Session

from app.editing.adapter import EditorOperation, execute_operation
from app.editing.persistence import ProjectRepository
from app.editing.registry import default_registry
from app.editing.timeline import Asset, Project, new_id
from app.models.audit import AuditLog


def inspect_asset(path: str, note: str | None = None) -> Asset:
    inspected = execute_operation(
        default_registry.create("ffmpeg"), EditorOperation.IMPORT_MEDIA, {"paths": [path]},
    )[0]
    return Asset(
        id=new_id(), name=Path(inspected["path"]).name, path=inspected["path"],
        kind=inspected["kind"], duration_seconds=inspected["duration_seconds"],
        metadata={"streams": inspected["streams"]}, note=note,
    )


def commit_imports(
    session: Session, project_id: str, assets: list[Asset], action: str,
    failures: list[str] | None = None, *, unique_copies: bool = False,
) -> None:
    repository = ProjectRepository(session)
    repository.begin_write()
    project = repository.get(project_id)
    if unique_copies:
        used = {asset.name.casefold() for asset in project.assets}
        for asset in assets:
            assert asset.path is not None  # inspection only returns local file assets
            source = Path(asset.path)
            target = source
            index = 0
            while target.name.casefold() in used or (target != source and target.exists()):
                index += 1
                target = source.with_name(f"{source.stem}-{index}{source.suffix}")
            if target != source:
                source.rename(target)
                asset.path = str(target)
                asset.name = target.name
            used.add(asset.name.casefold())
    if assets:
        repository.stage(Project.model_validate({**project.model_dump(), "assets": [*project.assets, *assets]}))
    for asset in assets:
        session.add(AuditLog(plugin_id="ffmpeg", action=action, status="ok",
                             detail=f"Proyecto {project_id}: recurso {asset.id}"))
    for code in failures or []:
        session.add(AuditLog(plugin_id="ffmpeg", action=action, status="error",
                             detail=f"Proyecto {project_id}: {code}"))
    session.commit()
