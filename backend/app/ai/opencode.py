from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event

import httpx

from app.ai.errors import (
    AIAuthFailed, AIError, AIModelRequired, AIProviderUnavailable, AIServerUnavailable, AITimeout,
    AICancelled, AIUnsupportedInput,
)

_DENY_ALL = [{"action": "*", "resource": "*", "effect": "deny"}]
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}")
_SESSION_ID = re.compile(r"ses_[a-zA-Z0-9_-]+")
_URL = re.compile(r"http://127\.0\.0\.1(?::[0-9]{1,5})?/?")
_VISION_MEDIA = frozenset({"image/jpeg"})


@dataclass(frozen=True)
class StudioModel:
    provider_id: str
    model_id: str
    inputs: frozenset[str] = frozenset({"text"})

    @property
    def key(self) -> str:
        return f"{self.provider_id}/{self.model_id}"

    @property
    def accepts_images(self) -> bool:
        return "image" in self.inputs

    def ref(self) -> dict[str, str]:
        return {"providerID": self.provider_id, "id": self.model_id}

    @classmethod
    def from_server(cls, item: object) -> StudioModel | None:
        if not isinstance(item, dict) or item.get("enabled") is not True or item.get("type", "chat") != "chat":
            return None
        provider, model = item.get("providerID"), item.get("id")
        if (isinstance(provider, str) and "/" not in provider and _ID.fullmatch(provider)
                and isinstance(model, str) and _ID.fullmatch(model)):
            capabilities = item.get("capabilities")
            advertised = capabilities.get("input") if isinstance(capabilities, dict) else None
            inputs = (frozenset(entry for entry in advertised if isinstance(entry, str))
                      if isinstance(advertised, list) else frozenset({"text"}))
            return cls(provider, model, inputs or frozenset({"text"}))
        return None


def _unavailable(model: StudioModel) -> AIProviderUnavailable:
    return AIProviderUnavailable(
        f"El proveedor de {model.key} no está disponible (HTTP 503). "
        "Reintenta más tarde o elige otro modelo."
    )


def _assistant_text(data: object, model: StudioModel) -> str:
    """Extrae solo texto; cualquier herramienta o parte desconocida rechaza el lote."""
    if not isinstance(data, list):
        raise AIError("OpenCode no devolvió mensajes válidos para el análisis.")
    texts: list[str] = []
    found = False
    for item in data:
        if not isinstance(item, dict) or item.get("type") != "assistant":
            continue
        found = True
        if (error := item.get("error")) is not None:
            details = error.get("data") if isinstance(error, dict) else None
            for entry in (error, details):
                if isinstance(entry, dict) and any(entry.get(key) == 503 for key in ("status", "statusCode")):
                    raise _unavailable(model)
            raise AIError("El modelo de OpenCode devolvió un error al analizar la imagen.")
        if item.get("finish") not in (None, "stop"):
            raise AIError("OpenCode no completó el análisis de la imagen.")
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                raise AIError("OpenCode devolvió contenido no válido al analizar la imagen.")
            kind = part.get("type")
            if kind == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif kind in {"reasoning", "step-start", "step-finish"}:
                continue
            else:
                raise AIError("OpenCode usó una herramienta o contenido no textual en el análisis. "
                              "Se rechazó la respuesta.")
    text = "\n".join(texts).strip()
    if not found or not text:
        raise AIError("OpenCode no devolvió descripciones para las imágenes.")
    return text



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
    def _request(client: httpx.Client, method: str, path: str, *,
                 generation_model: StudioModel | None = None, **kwargs) -> httpx.Response:
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
            if generation_model is not None:
                try:
                    error = OpenCodeServerProvider._json(response)
                except AIError:
                    error = {}
                data = error.get("data", {})
                errors = (error, data) if isinstance(data, dict) else (error,)
                if any(e.get("status") in (401, 403) or e.get("reason") == "authentication" for e in errors):
                    raise AIAuthFailed("El modelo de OpenCode rechazó la autenticación. Revisa el login.")
                if response.status_code == 503:
                    raise _unavailable(generation_model)
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

    def _catalog(self, client: httpx.Client) -> dict[str, StudioModel]:
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
        return models

    def list_models(self) -> dict:
        with self._client() as client:
            models = self._catalog(client)
        # Do not relay provider payloads (they can include credentials and paths).
        return {
            "models": list(models),
            "default_model": self.model if self.model in models else None,
            "vision_models": [key for key, model in models.items() if model.accepts_images],
        }

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
                generation_model=model,
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

    def _vision_model(self, client: httpx.Client) -> StudioModel:
        if self.model is None:
            raise AIModelRequired("Pulsa Cargar modelos y elige un modelo de OpenCode con entrada de imagen.")
        models = self._catalog(client)
        model = models.get(self.model)
        if model is None:
            raise AIModelRequired("El modelo de OpenCode solicitado no está disponible. "
                                  "Pulsa Cargar modelos y elige otro.")
        if not model.accepts_images:
            raise AIUnsupportedInput(
                f"El modelo {self.model} no acepta imágenes. Elige un modelo con entrada de imagen."
            )
        return model

    def ensure_vision(self) -> None:
        """Falla antes de preparar copias si el modelo no puede recibir imágenes."""
        with self._client() as client:
            self._vision_model(client)

    def _describe(self, client: httpx.Client, model: StudioModel, images: list[dict[str, str]],
                  system: str, prompt: str, cancel: Event | None = None) -> str:
        def check_cancel() -> None:
            if cancel is not None and cancel.is_set():
                raise AICancelled("Análisis cancelado.")

        for image in images:
            if (not isinstance(image, dict) or image.get("media_type") not in _VISION_MEDIA
                    or not isinstance(image.get("data"), str) or not image["data"]):
                raise AIError("Se intentó enviar una imagen con un formato no admitido.")
        check_cancel()
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
            check_cancel()
            if created.get("permissions") != _DENY_ALL:
                raise AIError("OpenCode no confirmó el bloqueo de herramientas.")
            selected = created.get("model")
            if not isinstance(selected, dict) or any(selected.get(k) != v for k, v in model.ref().items()):
                raise AIError("OpenCode no confirmó el modelo solicitado.")
            # /generate no acepta archivos; /prompt sí, y la sesión deny-all impide
            # que el agente use herramientas. Cada imagen va etiquetada por posición.
            files = [
                {"uri": f"data:{image['media_type']};base64,{image['data']}",
                 "name": f"imagen-{index}.jpg"}
                for index, image in enumerate(images, start=1)
            ]
            deadline = time.monotonic() + self.timeout
            self._json(self._request(
                client, "POST", f"{path}/prompt", generation_model=model,
                json={"text": f"{system}\n\n{prompt}", "files": files},
            ))
            while True:
                check_cancel()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AITimeout("OpenCode superó el tiempo de espera configurado.")
                try:
                    self._request(client, "POST", f"/api/experimental/session/{session_id}/wait",
                                  generation_model=model,
                                  timeout=min(remaining, 0.5) if cancel is not None else remaining)
                    break
                except AITimeout:
                    if cancel is None or time.monotonic() >= deadline:
                        raise
                    cancel.wait(0.05)
            check_cancel()
            data = self._json(self._request(client, "GET", f"{path}/message",
                                            generation_model=model)).get("data")
            text = _assistant_text(data, model)
            completed = True
        finally:
            try:
                self._request(client, "DELETE", path, timeout=3)
            except AIError:
                if completed:
                    raise AIError("OpenCode respondió, pero no se pudo eliminar la sesión del análisis.") from None
        return text

    def describe_images(self, images: list[dict[str, str]], system: str, prompt: str,
                        *, cancel: Event | None = None) -> str:
        with self._client() as client:
            model = self._vision_model(client)
            return self._describe(client, model, images, system, prompt, cancel)

    def generate_text(self, prompt: str, system: str) -> str:
        return self._complete(prompt, system)

    def _complete(self, prompt: str, system: str, *, verify: bool = False) -> str:
        if self.model is None:
            raise AIModelRequired("Pulsa Cargar modelos y elige un modelo de OpenCode antes de continuar.")
        with self._client() as client:
            models = self._catalog(client)
            if self.model not in models:
                raise AIModelRequired("El modelo de OpenCode solicitado no está disponible. "
                                      "Pulsa Cargar modelos y elige otro.")
            return self._generate(client, models[self.model], prompt, system, verify=verify)

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
