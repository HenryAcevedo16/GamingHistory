"""Multipart uploads stay inside the local workspace before becoming assets."""

import sqlite3
from urllib.parse import urlsplit

from anyio import CancelScope
from fastapi import APIRouter, Depends, Request
from python_multipart.exceptions import MultipartParseError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.config import settings
from app.core.db import get_session
from app.core.errors import InvalidOperation, StudioError
from app.editing.media_import import commit_imports, inspect_asset
from app.editing.persistence import ProjectRepository
from app.editing.uploads import CHUNK_BYTES, StreamingUpload, UploadIssue, UploadResult, storage_issue

router = APIRouter(prefix="/projects", tags=["projects"])
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def check_project(session: Session, project_id: str) -> None:
    ProjectRepository(session).get_record(project_id)
    session.rollback()


def publish(batch: StreamingUpload, session: Session, project_id: str) -> None:
    assets = [entry.result.asset for entry in batch.entries if entry.result.asset is not None]
    errors = [entry.result.error.code for entry in batch.entries if entry.result.error is not None]
    commit_imports(session, project_id, assets, "upload_media", errors, unique_copies=True)
    batch.keep = bool(assets)


@router.post("/{project_id}/assets/upload", response_model=list[UploadResult], openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {
        "description": "En orden: cada parte files puede ir seguida inmediatamente de su parte note (texto UTF-8).",
        "schema": {"type": "object", "required": ["files"], "properties": {
            "files": {"type": "array", "items": {"type": "string", "format": "binary"}},
        }},
    }}},
})
async def upload_assets(
    project_id: str, request: Request, session: Session = Depends(get_session),
) -> list[UploadResult]:
    # A cross-site HTML form cannot add this header; browser clients require CORS preflight.
    origin = request.headers.get("origin")
    if (request.headers.get("X-GHS-Upload") != "1" or request.url.hostname not in _LOOPBACK or
        (origin is not None and (origin not in settings.cors_origins or urlsplit(origin).hostname not in _LOOPBACK))):
        raise StudioError("La subida requiere Studio local y la cabecera X-GHS-Upload: 1.",
                          status_code=403, code="UPLOAD_HEADER")
    await run_in_threadpool(check_project, session, project_id)
    batch = None
    try:
        batch = await run_in_threadpool(StreamingUpload, request.headers.get("content-type", ""))
        async for data in request.stream():
            if not batch.done:
                for offset in range(0, len(data), CHUNK_BYTES):
                    await run_in_threadpool(batch.parser.write, data[offset:offset + CHUNK_BYTES])
                    if batch.done:
                        break
        if not batch.done or not batch.entries:
            raise InvalidOperation("La subida no contiene archivos o terminó incompleta.", code="UPLOAD_MULTIPART")
        for entry in batch.entries:
            if await request.is_disconnected():
                raise ClientDisconnect
            if entry.path is None:
                continue
            try:
                entry.result.asset = await run_in_threadpool(inspect_asset, str(entry.path), entry.note)
                entry.result.ok = True
            except StudioError as exc:
                await run_in_threadpool(entry.path.unlink)
                entry.result.error = UploadIssue(code=exc.code, message=exc.message)
        if await request.is_disconnected():
            raise ClientDisconnect
        await run_in_threadpool(publish, batch, session, project_id)
        return [entry.result for entry in batch.entries]
    except ClientDisconnect:
        raise StudioError("Subida cancelada: no se importó el lote.", code="UPLOAD_CANCELLED", status_code=499) from None
    except MultipartParseError:
        raise InvalidOperation("El cuerpo multipart es inválido.", code="UPLOAD_MULTIPART") from None
    except OSError as exc:
        issue = storage_issue(exc)
        raise StudioError(issue.message, code=issue.code, status_code=507 if issue.code == "UPLOAD_DISK_FULL" else 500) from exc
    except SQLAlchemyError as exc:
        if getattr(getattr(exc, "orig", None), "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
            raise StudioError("No hay espacio para guardar los recursos en SQLite.", code="UPLOAD_DISK_FULL", status_code=507) from exc
        raise StudioError("No se pudieron guardar los recursos en la base.", code="UPLOAD_SAVE_FAILED", status_code=500) from exc
    finally:
        if batch is not None:
            with CancelScope(shield=True):
                await run_in_threadpool(batch.cleanup)
