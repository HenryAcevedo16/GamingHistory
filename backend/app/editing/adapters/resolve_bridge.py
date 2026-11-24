"""Minimal client for the authenticated in-app DaVinci Resolve bridge.

The bridge is a script that runs *inside* Resolve and listens on loopback. It is
the only channel that reaches the free edition, because external scripting is a
Studio feature. This client intentionally reimplements only the wire contract
(HMAC-signed JSON lines, one request per connection); it does not import the
external MCP project.

The shared token is read from the bridge configuration and is never logged,
echoed in an error, or stored anywhere else.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.errors import CapabilityNotAvailable, DependencyUnavailable, InvalidOperation

PROTOCOL_VERSION = "1.0"
MAX_REQUEST_BYTES = 1_048_576
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "davinci-resolve-mcp" / "bridge.json"
ENV_CONFIG_PATH = "DAVINCI_RESOLVE_BRIDGE_CONFIG"


class ResolveBridgeUnavailable(DependencyUnavailable):
    """The bridge cannot be reached or its configuration is unusable."""


class ResolveBridgeCallError(InvalidOperation):
    """The bridge refused the request or Resolve failed the operation."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            f"DaVinci Resolve rechazó la operación ({code}): {message}",
            details={"bridge_code": code, **(details or {})},
        )
        self.bridge_code = code


def config_path() -> Path:
    override = os.environ.get(ENV_CONFIG_PATH)
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_bridge_config(path: Path | None = None) -> dict[str, Any]:
    """Read host/port/token. Never include the token in an error message."""
    target = path or config_path()
    try:
        with target.open(encoding="utf-8") as reader:
            data = json.loads(reader.read(65537))
    except (OSError, ValueError):
        raise ResolveBridgeUnavailable(
            "No se pudo leer la configuración del puente de Resolve. Comprueba DAVINCI_RESOLVE_BRIDGE_CONFIG."
        ) from None

    if not isinstance(data, dict):
        raise ResolveBridgeUnavailable("La configuración del puente no es un objeto JSON.")
    host = data.get("host")
    port = data.get("port")
    token = data.get("token")
    if host != "127.0.0.1":
        raise ResolveBridgeUnavailable("El puente debe estar configurado en 127.0.0.1.")
    if type(port) is not int or not 0 < port < 65536:
        raise ResolveBridgeUnavailable("La configuración del puente no define un 'port' válido.")
    if not isinstance(token, str) or not token:
        raise ResolveBridgeUnavailable("La configuración del puente no define 'token'.")
    return {"host": host, "port": int(port), "token": token}


def canonical_request(request: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in request.items() if key != "signature"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sign_request(token: str, request: dict[str, Any]) -> str:
    return hmac.new(token.encode("utf-8"), canonical_request(request), hashlib.sha256).hexdigest()


class ResolveBridgeClient:
    """One signed request per connection; honest about every failure."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self.timeout = float(timeout)

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            self._config = load_bridge_config()
        return self._config

    def request(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        config = self.config
        if config.get("host") != "127.0.0.1":
            raise ResolveBridgeUnavailable("El puente debe estar configurado en 127.0.0.1.")
        payload: dict[str, Any] = {
            "protocol": PROTOCOL_VERSION,
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "nonce": secrets.token_urlsafe(24),
            "operation": operation,
            "arguments": dict(arguments or {}),
        }
        payload["signature"] = sign_request(config["token"], payload)
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        if len(line) > MAX_REQUEST_BYTES:
            raise InvalidOperation("La petición al puente de Resolve supera el límite de 1 MiB.")

        address = (config["host"], int(config["port"]))
        try:
            sock = socket.create_connection(address, timeout=self.timeout)
        except OSError as exc:
            raise ResolveBridgeUnavailable(
                "No se puede alcanzar el puente de Resolve en "
                f"{address[0]}:{address[1]}. Inicia Workspace > Scripts > resolve_bridge.",
                details={"host": address[0], "port": address[1]},
            ) from exc

        try:
            sock.settimeout(self.timeout)
            sock.sendall(line)
            reader = sock.makefile("rb")
            try:
                raw = reader.readline(MAX_REQUEST_BYTES + 1)
            finally:
                reader.close()
        except (TimeoutError, socket.timeout) as exc:
            raise ResolveBridgeCallError(
                "bridge_timeout",
                "Resolve no respondió a tiempo; comprueba si hay un diálogo modal abierto.",
            ) from exc
        except OSError as exc:
            raise ResolveBridgeUnavailable(
                "La conexión con el puente de Resolve se interrumpió."
            ) from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass

        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "el puente no devolvió una línea completa dentro del límite."
            )
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "el puente devolvió JSON inválido."
            ) from exc
        if not isinstance(response, dict):
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "el puente devolvió una respuesta no-objeto."
            )
        if response.get("id") != payload["id"]:
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "el id de la respuesta no coincide con la petición."
            )
        if response.get("ok") is not True:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if code not in ("capability_unavailable", "stale_handle", "unauthorized", "no_project", "resolve_raised"):
                code = "bridge_error"
            raise ResolveBridgeCallError(
                code, "el puente rechazó la operación.",
            )
        return response.get("result")

    def health(self) -> dict[str, Any]:
        result = self.request("health", {})
        if not isinstance(result, dict):
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "health no devolvió un objeto."
            )
        return result

    def call_encoded(self, target: str, method: str, *args: Any) -> dict[str, Any]:
        """Return the bridge's `{value, truncated?}` envelope for one method call."""
        try:
            result = self.request("call", {"target": target, "method": method, "args": list(args)})
        except ResolveBridgeCallError as exc:
            if exc.bridge_code == "capability_unavailable":
                raise CapabilityNotAvailable(method, plugin_id="davinci-resolve") from None
            raise
        if not isinstance(result, dict) or "value" not in result:
            raise ResolveBridgeCallError(
                "bridge_protocol_error", "call no devolvió el sobre esperado."
            )
        return result

    def call(self, target: str, method: str, *args: Any) -> Any:
        return self.call_encoded(target, method, *args)["value"]

    def named(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.request(operation, arguments or {})
