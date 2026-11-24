"""EditorAdapter contract.

The contract is deliberately honest: every operation exists, and every
operation an adapter does not support raises CapabilityNotAvailable. There is
no default success path and no placeholder result.

A concrete adapter (FFmpeg, VectCutAPI, DaVinci Resolve, Descript, ...) lives
outside the core and only needs to override the methods it really implements.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import (
    CapabilityNotAvailable,
    InvalidOperation,
    PluginNotConnected,
)


def _plugin_is_connected(plugin_id: str) -> bool:
    """Read execution eligibility from persisted plugin lifecycle state."""
    from sqlmodel import Session

    from app.core.db import engine
    from app.models.plugin import PluginState

    with Session(engine) as session:
        state = session.get(PluginState, plugin_id)
        return bool(state is not None and state.enabled and state.connected)


class EditorOperation(str, Enum):
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    HEALTH_CHECK = "health_check"
    GET_CAPABILITIES = "get_capabilities"
    IMPORT_MEDIA = "import_media"
    CREATE_PROJECT = "create_project"
    CREATE_TIMELINE = "create_timeline"
    ADD_TRACK = "add_track"
    ADD_CLIP = "add_clip"
    UPDATE_CLIP = "update_clip"
    REMOVE_CLIP = "remove_clip"
    ADD_AUDIO = "add_audio"
    ADD_SUBTITLES = "add_subtitles"
    ADD_EFFECT = "add_effect"
    RENDER_PREVIEW = "render_preview"
    RENDER_FINAL = "render_final"
    EXPORT_PROJECT = "export_project"
    GET_JOB_STATUS = "get_job_status"


class AdapterCapabilities(BaseModel):
    """What this adapter instance can really execute.

    `operations` is the allow-list the central wrapper enforces before any
    method call. It must reflect reality, not the manifest's aspirations.
    """

    model_config = ConfigDict(extra="forbid")

    operations: set[EditorOperation] = Field(default_factory=set)
    verified: bool = False
    capability_ids: set[str] | None = None
    notes: list[str] = Field(default_factory=list)


class EditorAdapter(ABC):
    """Base class for every editor integration."""

    def __init__(self, plugin_id: str, config: dict[str, Any] | None = None) -> None:
        self.plugin_id = plugin_id
        self.config = dict(config or {})

    # -- identity / lifecycle ---------------------------------------------

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """Return the operations this adapter can execute right now."""

    def connect(self) -> None:
        self._unsupported(EditorOperation.CONNECT)

    def disconnect(self) -> None:
        self._unsupported(EditorOperation.DISCONNECT)

    def health_check(self) -> bool:
        self._unsupported(EditorOperation.HEALTH_CHECK)

    # -- editing operations ------------------------------------------------

    def import_media(self, paths: list[str]) -> Any:
        self._unsupported(EditorOperation.IMPORT_MEDIA)

    def create_project(self, name: str, **options: Any) -> Any:
        self._unsupported(EditorOperation.CREATE_PROJECT)

    def create_timeline(self, project_id: str, name: str, **options: Any) -> Any:
        self._unsupported(EditorOperation.CREATE_TIMELINE)

    def add_track(self, timeline_id: str, track: dict[str, Any]) -> Any:
        self._unsupported(EditorOperation.ADD_TRACK)

    def add_clip(self, timeline_id: str, clip: dict[str, Any]) -> Any:
        self._unsupported(EditorOperation.ADD_CLIP)

    def update_clip(self, timeline_id: str, clip_id: str, changes: dict[str, Any]) -> Any:
        self._unsupported(EditorOperation.UPDATE_CLIP)

    def remove_clip(self, timeline_id: str, clip_id: str) -> Any:
        self._unsupported(EditorOperation.REMOVE_CLIP)

    def add_audio(self, timeline_id: str, audio: dict[str, Any]) -> Any:
        self._unsupported(EditorOperation.ADD_AUDIO)

    def add_subtitles(self, timeline_id: str, cues: list[dict[str, Any]]) -> Any:
        self._unsupported(EditorOperation.ADD_SUBTITLES)

    def add_effect(self, timeline_id: str, clip_id: str, effect: dict[str, Any]) -> Any:
        self._unsupported(EditorOperation.ADD_EFFECT)

    def render_preview(self, timeline_id: str, **options: Any) -> Any:
        self._unsupported(EditorOperation.RENDER_PREVIEW)

    def render_final(self, timeline_id: str, **options: Any) -> Any:
        self._unsupported(EditorOperation.RENDER_FINAL)

    def export_project(self, timeline_id: str, target: str, **options: Any) -> Any:
        self._unsupported(EditorOperation.EXPORT_PROJECT)

    def get_job_status(self, job_id: str) -> Any:
        self._unsupported(EditorOperation.GET_JOB_STATUS)

    # -- helpers -----------------------------------------------------------

    def _unsupported(self, operation: EditorOperation) -> None:
        raise CapabilityNotAvailable(operation.value, plugin_id=self.plugin_id)

    def describe(self) -> dict[str, Any]:
        capabilities = self.get_capabilities()
        return {
            "plugin_id": self.plugin_id,
            "operations": sorted(operation.value for operation in capabilities.operations),
            "verified": capabilities.verified,
            "notes": capabilities.notes,
        }


def _coerce_operation(operation: EditorOperation | str) -> EditorOperation:
    if isinstance(operation, EditorOperation):
        return operation
    try:
        return EditorOperation(operation)
    except ValueError as exc:
        raise InvalidOperation(
            f"Operación desconocida: '{operation}'.",
            details={
                "operation": operation,
                "available_operations": [item.value for item in EditorOperation],
            },
        ) from exc


def execute_operation(
    adapter: EditorAdapter,
    operation: EditorOperation | str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Central gate: capabilities first, then the actual adapter method.

    This is the only sanctioned entry point for running an operation. It
    refuses unsupported operations and disconnected plugins instead of
    returning a simulated result.
    """
    op = _coerce_operation(operation)

    if not _plugin_is_connected(adapter.plugin_id):
        raise PluginNotConnected(
            "El plugin no está conectado o está deshabilitado; la operación no se ejecuta.",
            details={"plugin_id": adapter.plugin_id, "operation": op.value},
        )

    capabilities = adapter.get_capabilities()
    if op not in capabilities.operations:
        raise CapabilityNotAvailable(op.value, plugin_id=adapter.plugin_id)

    method = getattr(adapter, op.value)
    kwargs = dict(params or {})
    try:
        inspect.signature(method).bind(**kwargs)
    except TypeError as exc:
        raise InvalidOperation(
            f"Argumentos inválidos para '{op.value}': {exc}",
            details={"plugin_id": adapter.plugin_id, "operation": op.value},
        ) from exc

    return method(**kwargs)
