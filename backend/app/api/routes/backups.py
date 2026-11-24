from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field as ColumnField
from sqlmodel import Session, SQLModel, select

from app.backup.destination import LocalDestination
from app.backup.format import BackupError
from app.backup.service import BackupService
from app.core.config import settings
from app.core.db import get_session
from app.core.errors import StudioError
from app.editing.timeline import StrictModel
from app.models.audit import AuditLog

router = APIRouter(prefix="/backups", tags=["backups"])
AUDIT_ID = "backup-local"


class BackupSettings(SQLModel, table=True):
    __tablename__ = "backup_settings"

    id: int = ColumnField(default=1, primary_key=True)
    folder: str


class Configure(StrictModel):
    folder: str = Field(min_length=1, max_length=4096)


class Preview(StrictModel):
    project_id: str = Field(min_length=1, max_length=255)
    include_assets: StrictBool = False


class Create(Preview):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: StrictBool = False


def _configured(session: Session):
    row = session.get(BackupSettings, 1)
    return row.folder if row else settings.backup_dir


def _service(session: Session) -> BackupService:
    folder = _configured(session)
    if not folder:
        raise BackupError("Configura primero una carpeta local.", code="BACKUP_NOT_CONFIGURED")
    return BackupService(session, LocalDestination(folder))


@contextmanager
def _audit(session: Session, action: str):
    outcome = {"detail": ""}
    try:
        yield outcome
    except StudioError as exc:
        session.rollback()
        session.add(AuditLog(plugin_id=AUDIT_ID, action=action, status="denied", detail=exc.code))
        session.commit()
        raise
    except (OSError, ValueError, SQLAlchemyError):
        session.rollback()
        session.add(AuditLog(plugin_id=AUDIT_ID, action=action, status="error", detail="BACKUP_OPERATION_FAILED"))
        session.commit()
        raise BackupError("No se pudo completar la operación. Revisa la ruta, los permisos y el disco.",
                          code="BACKUP_OPERATION_FAILED") from None
    else:
        session.add(AuditLog(plugin_id=AUDIT_ID, action=action, detail=outcome["detail"]))
        session.commit()


@router.get("/settings")
def get_settings(session: Session = Depends(get_session)) -> dict:
    folder = _configured(session)
    if not folder:
        return {"status": "not_configured", "location": "", "free_bytes": None}
    try:
        state = LocalDestination(folder).state()
    except BackupError as exc:
        return {"status": "error", "location": str(folder), "free_bytes": None, "error": exc.message}
    except OSError:
        return {"status": "error", "location": str(folder), "free_bytes": None,
                "error": "La carpeta no está disponible."}
    return {"status": "ready", **asdict(state)}


@router.put("/settings")
def configure(payload: Configure, session: Session = Depends(get_session)) -> dict:
    with _audit(session, "configurar"):
        destination = LocalDestination(payload.folder)
        destination.prepare()
        state = destination.state()
        row = session.get(BackupSettings, 1) or BackupSettings(folder=state.location)
        row.folder = state.location
        session.add(row)
        return {"status": "ready", **asdict(state)}


@router.post("/preview")
def preview(payload: Preview, session: Session = Depends(get_session)) -> dict:
    with _audit(session, "vista previa"):
        return _service(session).plan(payload.project_id, payload.include_assets).preview


@router.post("", status_code=201)
def create(payload: Create, session: Session = Depends(get_session)) -> dict:
    with _audit(session, "guardar") as event:
        if not payload.confirmed:
            raise BackupError("Confirma la vista previa para crear el respaldo.", status_code=409,
                              code="BACKUP_CONFIRMATION_REQUIRED")
        result = _service(session).create(payload.project_id, payload.include_assets,
                                          payload.revision, payload.confirmed)
        event["detail"] = result["id"]
        return result


@router.get("")
def list_backups(session: Session = Depends(get_session)) -> dict:
    with _audit(session, "listar") as event:
        items = _service(session).list()
        invalid = sum(item["verification"] == "invalid" for item in items)
        event["detail"] = f"{len(items)} respaldos; {invalid} manifiestos inválidos"
        return {"items": items}


@router.get("/audit", response_model=list[AuditLog])
def history(session: Session = Depends(get_session)):
    return session.exec(select(AuditLog).where(AuditLog.plugin_id == AUDIT_ID)
                        .order_by(AuditLog.id.desc()).limit(50)).all()


@router.post("/{backup_id}/verify")
def verify(backup_id: str, session: Session = Depends(get_session)) -> dict:
    with _audit(session, "verificar") as event:
        result = _service(session).verify(backup_id)
        event["detail"] = result["id"]
        return result


@router.post("/{backup_id}/restore", status_code=201)
def restore(backup_id: str, session: Session = Depends(get_session)) -> dict:
    with _audit(session, "restaurar") as event:
        copy = _service(session).restore(backup_id)
        event["detail"] = backup_id
        return {"id": copy.id, "name": copy.name}
