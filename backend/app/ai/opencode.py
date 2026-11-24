from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx

from app.ai.errors import AIAuthFailed, AIError, AIServerUnavailable, AITimeout

_DENY_ALL = [{"action": "*", "resource": "*", "effect": "deny"}]
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}")
_SESSION_ID = re.compile(r"ses_[a-zA-Z0-9_-]+")
_URL = re.compile(r"http://127\.0\.0\.1(?::[0-9]{1,5})?/?")


@dataclass(frozen=True)
class StudioModel:
    provider_id: str
    model_id: str

    @property
    def key(self) -> str:
        return f"{self.provider_id}/{self.model_id}"

    def ref(self) -> dict[str, str]:
        return {"providerID": self.provider_id, "id": self.model_id}

    @classmethod
    def from_server(cls, item: object) -> StudioModel | None:
        if not isinstance(item, dict) or item.get("enabled") is not True or item.get("type", "chat") != "chat":
            return None
        provider, model = item.get("providerID"), item.get("id")
        if (isinstance(provider, str) and "/" not in provider and _ID.fullmatch(provider)
                and isinstance(model, str) and _ID.fullmatch(model)):
            return cls(provider, model)
        return None


class OpenCodeServerProvider:
    """OpenCode V2 HTTP API; no agent loop, tool calls, or project context."""

    def __init__(self, url: str, password: str, timeout: float,
                 model: str | None = None, *, default_model: str | None = None):
        self.url = url
        self.password = password
        self.timeout = timeout
        self.model = model or default_model

    @contextmanager
    def _client(self) -> Iterator[httpx.Client]:
        if not _URL.fullmatch(self.url):
            raise AIError("La URL de OpenCode debe ser HTTP y apuntar solo a 127.0.0.1.")
        try:
            port = httpx.URL(self.url).port
        except httpx.InvalidURL:
            raise AIError("El puerto de OpenCode no es válido.") from None
        if port is not None and not 1 <= port <= 65535:
            raise AIError("El puerto de OpenCode no es válido.")
        if not self.password.strip():
            raise AIAuthFailed("Falta GHS_OPENCODE_SERVER_PASSWORD en backend/.env.")
        with httpx.Client(base_url=self.url, timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 3)),
                          follow_redirects=False, trust_env=False) as client:
            try:
                self._request(client, "GET", "/api/info")
            except AIAuthFailed:
                pass  # This route must challenge unauthenticated clients.
            else:
                raise AIAuthFailed("El servidor OpenCode no exige contraseña; Studio no lo usará.")
            client.auth = ("opencode", self.password)
            yield client

    @staticmethod
    def _request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise AITimeout("OpenCode superó el tiempo de espera configurado.") from None
        except httpx.RequestError:
            raise AIServerUnavailable("OpenCode no está corriendo o no responde en 127.0.0.1.") from None
        if response.status_code in (401, 403):
            raise AIAuthFailed("OpenCode rechazó la contraseña del servidor.")
        if response.status_code in (408, 504):
            raise AITimeout("OpenCode superó el tiempo de espera configurado.")
        if not response.is_success:
            # For generation V2 may wrap an upstream authentication failure as
            # ProviderRequestError. Never expose raw provider bodies or settings.
            if path.endswith("/generate"):
                error = OpenCodeServerProvider._json(response)
                data = error.get("data", {})
                errors = (error, data) if isinstance(data, dict) else (error,)
                if any(e.get("status") in (401, 403) or e.get("reason") == "authentication" for e in errors):
                    raise AIAuthFailed("El modelo de OpenCode rechazó la autenticación. Revisa el login.")
            raise AIError("OpenCode no pudo completar la operación solicitada.")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            data = response.json()
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
        raise AIError("OpenCode no devolvió una respuesta válida de la API v2.")

    def _catalog(self, client: httpx.Client) -> tuple[dict[str, StudioModel], str | None]:
        # V2 documents that the first snapshot may precede initial plugin
        # settlement. Retry only empty snapshots, never a generation request.
        for attempt in range(4):
            data = self._json(self._request(client, "GET", "/api/model")).get("data")
            if not isinstance(data, list):
                raise AIError("OpenCode no devolvió un catálogo de modelos válido.")
            models = {m.key: m for item in data if (m := StudioModel.from_server(item))}
            if models:
                break
            if attempt < 3:
                time.sleep(0.5)
        if not models:
            providers = self._json(self._request(client, "GET", "/api/provider")).get("data")
            if providers == []:
                raise AIAuthFailed("OpenCode no tiene un proveedor activo con login o credenciales.")
            raise AIError("OpenCode no tiene modelos de chat disponibles.")
        if self.model is not None:
            return models, self.model if self.model in models else None
        data = self._json(self._request(client, "GET", "/api/model/default")).get("data")
        default = StudioModel.from_server(data)
        return models, default.key if default and default.key in models else None

    def list_models(self) -> dict:
        with self._client() as client:
            models, default = self._catalog(client)
        # Do not relay provider payloads (they can include credentials and paths).
        return {"models": list(models), "default_model": default}

    def _generate(self, client: httpx.Client, model: StudioModel, prompt: str, system: str,
                  *, verify: bool = False) -> str:
        created = self._json(self._request(
            client, "POST", "/api/session",
            json={"title": "Gaming History Studio", "model": model.ref(), "permissions": _DENY_ALL},
        )).get("data")
        session_id = created.get("id") if isinstance(created, dict) else None
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise AIError("OpenCode no devolvió una sesión válida.")
        path = f"/api/session/{session_id}"
        completed = False
        try:
            if created.get("permissions") != _DENY_ALL:
                raise AIError("OpenCode no confirmó el bloqueo de herramientas.")
            selected = created.get("model")
            if not isinstance(selected, dict) or any(selected.get(k) != v for k, v in model.ref().items()):
                raise AIError("OpenCode no confirmó el modelo solicitado.")
            # Unlike /prompt, /generate is transient text generation from
            # session history, not the agent loop. This fresh session is empty.
            data = self._json(self._request(
                client, "POST", f"{path}/generate",
                json={"prompt": f"{system}\n\nTexto del usuario:\n{prompt}"},
            )).get("data")
            text = data.get("text") if isinstance(data, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise AIError("OpenCode no devolvió texto.")
            if verify:
                for resource in ("message", "permission"):
                    data = self._json(self._request(client, "GET", f"{path}/{resource}")).get("data")
                    if data != []:
                        raise AIError("OpenCode no confirmó la sesión sin historial ni permisos pendientes.")
            completed = True
        finally:
            try:
                self._request(client, "DELETE", path, timeout=3)
            except AIError:
                # Preserve the original error if generation failed too.
                # A V2 /generate does not write the input to session history.
                if completed:
                    raise AIError("OpenCode respondió, pero no se pudo eliminar la sesión de Studio.") from None
        return text

    def generate_text(self, prompt: str, system: str) -> str:
        return self._complete(prompt, system)

    def _complete(self, prompt: str, system: str, *, verify: bool = False) -> str:
        with self._client() as client:
            models, default = self._catalog(client)
            if default is None:
                raise AIError("El modelo de OpenCode solicitado o predeterminado no está disponible. Elige uno del catálogo.")
            return self._generate(client, models[default], prompt, system, verify=verify)

    def check_status(self) -> dict:
        marker = self._complete(
            "Si no tienes herramientas, responde exactamente GHS_AI_READY. "
            "Si tienes herramientas, intenta leer el archivo phase9b-tool-probe.txt.",
            "Diagnóstico de texto sin herramientas. Devuelve solo el marcador si no tienes herramientas.",
            verify=True,
        )
        if marker.strip() != "GHS_AI_READY":
            raise AIError("OpenCode respondió, pero no pasó la prueba mínima de texto.")
        return {"ready": True, "tools_disabled": True}
