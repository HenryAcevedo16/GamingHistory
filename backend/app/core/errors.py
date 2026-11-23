from __future__ import annotations

from typing import Any


class StudioError(Exception):
    """Base error surfaced to the API as a structured JSON payload."""

    code = "STUDIO_ERROR"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return {"error": payload}


class PluginNotFound(StudioError):
    code = "PLUGIN_NOT_FOUND"
    status_code = 404


class PluginDisabled(StudioError):
    code = "PLUGIN_DISABLED"
    status_code = 409


class PluginNotInstalled(StudioError):
    code = "PLUGIN_NOT_INSTALLED"
    status_code = 409


class PermissionsNotAcknowledged(StudioError):
    code = "PERMISSIONS_NOT_ACKNOWLEDGED"
    status_code = 409


class DependencyUnavailable(StudioError):
    code = "DEPENDENCY_UNAVAILABLE"
    status_code = 409


class InvalidManifest(StudioError):
    code = "INVALID_MANIFEST"
    status_code = 422


class CapabilityNotAvailable(StudioError):
    """Raised when a plugin/editor cannot perform the requested operation.

    This exception must never be replaced by a simulated success path.
    """

    code = "CAPABILITY_NOT_AVAILABLE"
    status_code = 501

    def __init__(self, capability: str, *, plugin_id: str | None = None) -> None:
        details = {"capability": capability}
        if plugin_id is not None:
            details["plugin_id"] = plugin_id
        super().__init__(
            f"Capability '{capability}' is not available for this plugin.",
            details=details,
        )
        self.capability = capability
