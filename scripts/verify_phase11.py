"""Verificación real de la Fase 11: análisis de imágenes con proveedores reales.

Crea una imagen sintética «PRUEBA-7431» sobre naranja, la envía por la ruta
real de Studio (reducción, loteo, etiquetas, saneado y auditoría) y comprueba
que el proveedor describe la palabra o el color. No toca la base de datos real
ni deja temporales: usa SQLite en memoria y un workspace temporal.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["GHS_DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.ai.opencode import OpenCodeServerProvider
from app.ai.vision import OUTPUT_URL, TEMP_PREFIX
from app.api.routes import ai
from app.core.config import settings
from app.core.db import get_session
from app.core.exec import run_command
from app.editing.persistence import ProjectRepository
from app.editing.timeline import Asset, Project
from app.main import app
from app.models.audit import AuditLog

HEADERS = {"X-GHS-AI-Action": "confirm"}
DEFAULT_MODEL = "openai/gpt-6.2-sol"
FONT = r"C\\:/Windows/Fonts/arial.ttf"


def require(response):
    if not response.is_success:
        error = response.json().get("error", {})
        raise RuntimeError(f"{error.get('code', response.status_code)}: "
                           f"{error.get('message', 'Falló la solicitud.')}")
    return response.json()


def make_image(path: Path) -> None:
    draw = ("drawbox=x=0:y=0:w=iw:h=ih:color=orange@1.0:t=fill,"
            f"drawtext=fontfile={FONT}:text=PRUEBA-7431:fontcolor=white:fontsize=96:"
            "x=(w-text_w)/2:y=(h-text_h)/2")
    result = run_command(
        "ffmpeg",
        ["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "color=c=orange:s=1280x720", "-vf", draw, "-frames:v", "1", str(path)],
        timeout=30, allowed_binaries={"ffmpeg"},
    )
    if not result.ok or not path.is_file():
        raise RuntimeError("No se pudo generar la imagen sintética de prueba.")


def flat(text: str) -> str:
    return (unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower())


def check_result(result: dict) -> str:
    if result.get("status") != "ok":
        raise RuntimeError(f"{result.get('code')}: {result.get('message')}")
    description = result.get("description") or ""
    if len(description) > 500:
        raise RuntimeError("La descripción superó 500 caracteres sin recortar.")
    if OUTPUT_URL.search(description):
        raise RuntimeError("La descripción conserva una URL sin marcar.")
    if "enlace omitido" not in description and result.get("urls_removed"):
        raise RuntimeError("La descripción ocultó enlaces sin dejar la marca esperada.")
    normalized = flat(description)
    if "prueba-7431" not in normalized and "naranja" not in normalized:
        raise RuntimeError("La descripción no menciona la palabra ni el color.")
    return description


def verify(provider: str, model: str | None, engine, project_id: str, asset_id: str) -> None:
    observed = {"created": 0, "deleted": []}
    original = OpenCodeServerProvider._request
    original_temp = ai.TemporaryDirectory
    own_dirs: list[Path] = []

    def recording(client, method, path, **kwargs):
        response = original(client, method, path, **kwargs)
        if method == "POST" and path == "/api/session":
            observed["created"] += 1
        if method == "DELETE" and path.startswith("/api/session/"):
            observed["deleted"].append(response.status_code)
        return response

    def track_temp(*args, **kwargs):
        folder = original_temp(*args, **kwargs)
        own_dirs.append(Path(folder.name))
        return folder

    OpenCodeServerProvider._request = staticmethod(recording)
    ai.TemporaryDirectory = track_temp
    try:
        client = TestClient(app, base_url="http://127.0.0.1")
        try:
            selection = {"project_id": project_id, "asset_ids": [asset_id]}
            preview = require(client.post("/api/ai/vision/preview", json=selection))
            if preview["errors"] or preview["total_bytes"] <= 0 or preview["batches"] != 1:
                raise RuntimeError("No se pudo previsualizar el tamaño reducido.")
            if observed["created"]:
                raise RuntimeError("La previsualización no debe crear sesiones.")
            body = {**selection, "provider": provider, "confirmed": True}
            if model is not None:
                body["model"] = model
            result = require(client.post("/api/ai/vision", headers=HEADERS, json=body))
        finally:
            client.close()
    finally:
        OpenCodeServerProvider._request = staticmethod(original)
        ai.TemporaryDirectory = original_temp

    if len(own_dirs) != 2 or any(not p.name.startswith(TEMP_PREFIX) or p.exists() for p in own_dirs):
        raise RuntimeError("No se verificó la limpieza de los temporales de vista previa y análisis.")
    check_result(result["results"][0])
    if provider == "opencode" and observed["created"] != 1:
        raise RuntimeError("La operación no creó exactamente una sesión en OpenCode.")
    if provider == "opencode" and observed["deleted"] != [204]:
        raise RuntimeError(f"No se verificó el borrado de la sesión: {observed['deleted']}.")
    if result.get("images") != 1 or result.get("batches") != 1:
        raise RuntimeError("La respuesta no procesó una imagen en un lote.")
    if result["total_bytes"] != preview["total_bytes"]:
        raise RuntimeError("El total enviado no coincide con la reducción mostrada.")
    with Session(engine) as session:
        rows = session.exec(select(AuditLog).where(
            AuditLog.action == "analyze_images",
            AuditLog.plugin_id == ("opencode-ai" if provider == "opencode" else "claude-ai"),
        )).all()
        details = " ".join(row.detail or "" for row in rows)
        if not rows or details.count("proveedor=") < 2:
            raise RuntimeError("La auditoría no registró el inicio y el fin del análisis.")
        if "PRUEBA-7431" in details or "naranja" in details or "Descripción" in details:
            raise RuntimeError("La auditoría contiene texto de la imagen o de la descripción.")
        if str(settings.resolved_workspace_dir) in details:
            raise RuntimeError("La auditoría contiene rutas del workspace.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Modelo de OpenCode con entrada de imagen (por defecto {DEFAULT_MODEL}).")
    parser.add_argument("--claude", action="store_true", help="También prueba Claude Code (si tiene sesión).")
    args = parser.parse_args()
    for logger in ("httpx", "httpx2"):
        logging.getLogger(logger).setLevel(logging.WARNING)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    original_workspace = settings.workspace_dir
    failures: list[str] = []
    print(f"Fase 11: imagen sintética «PRUEBA-7431» sobre naranja, 1280x720, "
          f"reducción real a 1024 px antes de enviar.")
    try:
        with tempfile.TemporaryDirectory(prefix="ghs-verify11-") as folder:
            workspace = Path(folder)
            settings.workspace_dir = workspace
            image = workspace / "prueba-7431.png"
            make_image(image)
            before = hashlib.sha256(image.read_bytes()).hexdigest()
            with Session(engine) as session:
                repository = ProjectRepository(session)
                repository.begin_write()
                project = repository.save(Project(name="Verificación Fase 11", assets=[
                    Asset(id="prueba-7431", name=image.name, path=str(image), kind="image"),
                ]))
            try:
                verify("opencode", args.model, engine, project.id, "prueba-7431")
                print(f"Verificado OpenCode ({args.model}): reconoció el texto o el color.")
            except Exception as exc:
                failures.append(f"OpenCode: {exc}")
                print(f"No verificado OpenCode: {exc}")

            if args.claude:
                try:
                    verify("claude", None, engine, project.id, "prueba-7431")
                    print("Verificado Claude Code: reconoció el texto o el color.")
                except Exception as exc:
                    failures.append(f"Claude Code: {exc}")
                    print(f"No verificado Claude Code: {exc}")
            if hashlib.sha256(image.read_bytes()).hexdigest() != before:
                raise RuntimeError("La imagen original cambió durante la verificación.")
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
        settings.workspace_dir = original_workspace

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
