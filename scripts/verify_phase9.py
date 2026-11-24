"""Run real Claude Agent SDK calls against an isolated, in-process Studio API."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.ai.provider import worker_env
from app.core.db import get_session
from app.main import app
from app.models.audit import AuditLog

HEADERS = {"X-GHS-AI-Action": "confirm"}
SCRIPT = "Una cronista compara una consola portátil con su versión de sobremesa."
SRT = "1\n00:00:00,000 --> 00:00:02,000\nHola como estas\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suggestions", action="store_true", help="También prueba guion y SRT con texto sintético.")
    args = parser.parse_args()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    try:
        # A bogus parent credential makes accidental inheritance detectable.
        os.environ["ANTHROPIC_API_KEY"] = "phase9-test-parent-only-not-a-key"
        if any(key.upper() == "ANTHROPIC_API_KEY" for key in worker_env()):
            raise RuntimeError("El entorno del worker no está aislado.")
        app.dependency_overrides[get_session] = session_override
        # Do not enter the app lifespan: it initializes the real local DB.
        client = TestClient(app, base_url="http://localhost")
        if client.get("/api/ai/status").status_code != 403:
            raise RuntimeError("El diagnóstico no exigió una acción explícita.")
        response = client.get("/api/ai/status", headers=HEADERS)
        if not response.is_success:
            error = response.json().get("error", {})
            raise RuntimeError(f"{error.get('code', response.status_code)}: {error.get('message', 'Falló el diagnóstico.')}")
        status = response.json()
        if not all(status.get(check) is True for check in ("sdk_importable", "session_active", "tools_disabled", "ready")):
            raise RuntimeError("El diagnóstico no confirmó todos los requisitos.")
        print(f"Claude Code {status['cli_version']}: sesión claude.ai sin API key; prueba Read sin herramientas ni MCP.")
        expected_actions = ["status"]
        if args.suggestions:
            for route, label, payload, key in (
                ("script", "Guion", {"text": SCRIPT}, "text"),
                ("subtitles", "Corrección SRT", {"text": SRT, "mode": "correct"}, "cues"),
                ("subtitles", "Generación SRT", {"text": SRT, "mode": "generate"}, "cues"),
            ):
                response = client.post(f"/api/ai/{route}", headers=HEADERS, json={**payload, "confirmed": True})
                if not response.is_success:
                    error = response.json().get("error", {})
                    raise RuntimeError(f"{label}: {error.get('code', response.status_code)}: {error.get('message', 'Falló la sugerencia.')}")
                if not response.json().get(key):
                    raise RuntimeError(f"{label}: respuesta vacía.")
                expected_actions.append(f"suggest_{route}")
                print(f"{label}: sugerencia real recibida" + (" y SRT validado." if key == "cues" else "."))
        with Session(engine) as session:
            rows = session.exec(select(AuditLog).order_by(AuditLog.id)).all()
            if [(row.action, row.status, row.detail) for row in rows] != [
                (action, outcome, "") for action in expected_actions for outcome in ("started", "ok")
            ]:
                raise RuntimeError("La auditoría no coincide con las acciones esperadas.")
        print("Verificado: llamadas reales y auditoría sin texto de entrada ni de salida.")
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
