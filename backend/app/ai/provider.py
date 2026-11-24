from __future__ import annotations

import json
import os
import subprocess
import sys
from threading import Event
from typing import Protocol

from app.ai.errors import AICLINotFound, AICancelled, AIError, AINotLoggedIn, AITimeout
from app.core.config import BACKEND_ROOT


class AIProvider(Protocol):
    def generate_text(self, prompt: str, system: str) -> str: ...

    def describe_images(self, images: list[dict[str, str]], system: str, prompt: str,
                        *, cancel: Event | None = None) -> str: ...

    def ensure_vision(self) -> None: ...


# The SDK merges options.env with os.environ. Start a separate Python process with
# a positive allowlist instead of mutating the web server's shared environment.
_OS_ENV = frozenset({
    "PATH", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "COMSPEC", "LANG", "LC_ALL",
})
_ERRORS = {kind.code: kind for kind in (AICLINotFound, AINotLoggedIn, AITimeout, AIError)}


def worker_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in _OS_ENV}


class ClaudeAgentSDKProvider:
    def __init__(self, timeout: float, model: str | None = None):
        self.timeout = timeout
        self.model = model

    def _run(self, prompt: str, system: str, images: list[dict[str, str]] | None = None) -> dict:
        payload: dict[str, object] = {
            "prompt": prompt, "system": system, "timeout": self.timeout, "model": self.model,
        }
        if images:
            payload["images"] = images
        try:
            process = subprocess.run(
                [sys.executable, "-E", "-m", "app.ai.worker"],
                cwd=BACKEND_ROOT, env=worker_env(),
                input=json.dumps(payload).encode("utf-8"),
                capture_output=True, timeout=self.timeout + 5, check=True,
            )
            data = json.loads(process.stdout)
            if not isinstance(data, dict):
                raise ValueError
        except subprocess.TimeoutExpired:
            raise AITimeout("Claude superó el tiempo de espera configurado.") from None
        except (OSError, ValueError, subprocess.CalledProcessError):
            raise AIError("Falló el proceso local del Claude Agent SDK.") from None
        if data.get("error") in _ERRORS:
            raise _ERRORS[data["error"]](data["message"], details=data.get("checks"))
        if not isinstance(data.get("text"), str) or not data["text"].strip():
            raise AIError("El Claude Agent SDK no devolvió texto.")
        return data

    def generate_text(self, prompt: str, system: str) -> str:
        return self._run(prompt, system)["text"]

    def describe_images(self, images: list[dict[str, str]], system: str, prompt: str,
                        *, cancel: Event | None = None) -> str:
        if cancel is not None and cancel.is_set():
            raise AICancelled("Análisis cancelado.")
        return self._run(prompt, system, images)["text"]

    def ensure_vision(self) -> None:
        # Claude Code recibe bloques de imagen en el mismo mensaje; se comprobó
        # en real con herramientas desactivadas. No hay capacidades que consultar.
        return None

    def check_status(self) -> dict:
        # Check the CLI's actual tool inventory and challenge it to use Read.
        data = self._run(
            "Intenta usar Read para abrir phase9-tool-probe.txt. "
            "Si no tienes esa herramienta, responde exactamente GHS_AI_READY.",
            "Prueba de disponibilidad. Si no hay herramientas, da solo el marcador solicitado.",
        )
        checks = data["checks"]
        if data["text"].strip() != "GHS_AI_READY":
            raise AIError("Claude respondió, pero no pasó la prueba mínima.", details=checks)
        return {**checks, "ready": True}
