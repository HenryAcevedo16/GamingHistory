"""Verify Studio against a real, already running OpenCode V2 server."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.db import get_session
from app.main import app
from app.models.audit import AuditLog

HEADERS = {"X-GHS-AI-Action": "confirm"}
SRT = "1\n00:00:00,000 --> 00:00:02,000\nHola como estas\n"


def require_response(response):
    if not response.is_success:
        error = response.json().get("error", {})
        raise RuntimeError(f"{error.get('code', response.status_code)}: "
                           f"{error.get('message', 'Falló la solicitud.')}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="ID proveedor/modelo del catálogo. Si se omite, usa GHS_OPENCODE_MODEL.")
    parser.add_argument("--suggestions", action="store_true", help="También prueba guion y SRT con texto sintético.")
    args = parser.parse_args()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    try:
        app.dependency_overrides[get_session] = session_override
        # Do not enter the app lifespan: it initializes the real Studio DB.
        with_client = TestClient(app, base_url="http://127.0.0.1")
        try:
            if with_client.get("/api/ai/status?provider=opencode").status_code != 403:
                raise RuntimeError("El diagnóstico no exigió una acción explícita.")
            catalog = require_response(with_client.get("/api/ai/models", headers=HEADERS))
            model = args.model or catalog["default_model"]
            if model not in catalog["models"]:
                raise RuntimeError("AI_MODEL_REQUIRED: Elige un modelo del catálogo mediante GHS_OPENCODE_MODEL o --model.")
            params = {"provider": "opencode", "model": model}
            status = require_response(with_client.get("/api/ai/status", params=params, headers=HEADERS))["providers"]["opencode"]
            if not status["ready"]:
                raise RuntimeError(f"{status['code']}: {status['message']}")
            if status.get("tools_disabled") is not True:
                raise RuntimeError("El diagnóstico no confirmó el modo sin herramientas.")
            actions = ["list_models", "status"]
            if args.suggestions:
                for route, payload, key in (
                    ("script", {"text": "Una cronista compara dos consolas."}, "text"),
                    ("subtitles", {"text": SRT, "mode": "correct"}, "cues"),
                    ("subtitles", {"text": SRT, "mode": "generate"}, "cues"),
                ):
                    result = require_response(with_client.post(f"/api/ai/{route}", headers=HEADERS,
                                              json={**payload, **params, "confirmed": True}))
                    if not result.get(key):
                        raise RuntimeError(f"{route}: respuesta vacía.")
                    actions.append(f"suggest_{route}")
        finally:
            with_client.close()
        with Session(engine) as session:
            rows = session.exec(select(AuditLog).order_by(AuditLog.id)).all()
            if [(row.plugin_id, row.action, row.status, row.detail) for row in rows] != [
                ("opencode-ai", action, outcome, "") for action in actions for outcome in ("started", "ok")
            ]:
                raise RuntimeError("La auditoría no coincide con las acciones esperadas.")
        print(f"Verificado: OpenCode real ({model}), texto sin herramientas y auditoría sin contenido."
              + (" Guion y ambos modos SRT verificados." if args.suggestions else ""))
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"No verificado: {reason}")
        return 1
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
