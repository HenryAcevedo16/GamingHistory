"""DaVinci Resolve adapter driven by the authenticated in-app bridge.

Resolve Free has no external scripting host, so the only honest channel is the
bridge that runs inside the application. This adapter speaks to it directly and
refuses to claim anything the bridge did not confirm: every write checks the
boolean Resolve returned, and verified capabilities are persisted only after the
corresponding real operation completed.

The unified timeline is the source of truth. `ResolveConverter` plans that
mapping and reports every element it cannot express instead of dropping it.
"""

from __future__ import annotations

import os
from math import isfinite
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.core.errors import CapabilityNotAvailable, InvalidOperation
from app.editing.adapter import AdapterCapabilities, EditorAdapter, EditorOperation
from app.editing.adapters.resolve_bridge import (
    ResolveBridgeClient,
    ResolveBridgeUnavailable,
    ResolveBridgeCallError,
)
from app.editing.converters import ConversionResult, TimelineConverter, UnsupportedElement
from app.editing.registry import register_adapter
from app.editing.timeline import AudioTrack, Project, SubtitleTrack, VideoTrack
from app.models.plugin import PluginState

_IMPLEMENTED = {
    EditorOperation.HEALTH_CHECK,
    EditorOperation.GET_CAPABILITIES,
    EditorOperation.IMPORT_MEDIA,
    EditorOperation.CREATE_PROJECT,
    EditorOperation.CREATE_TIMELINE,
    EditorOperation.ADD_TRACK,
    EditorOperation.ADD_CLIP,
    EditorOperation.RENDER_PREVIEW,
    EditorOperation.RENDER_FINAL,
    EditorOperation.GET_JOB_STATUS,
}

_MEDIA_TYPES = {"video": 1, "audio": 2}
_CAPABILITY_IDS = {"project.inspect", "project.create", "media.import", "timeline.create", "track.add", "clip.add", "render", "job.status"}


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def _under(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def _engine():
    """Resolve the engine lazily so tests can swap the database binding."""
    from app.core.db import engine

    return engine


def _real_roots(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_norm(str(value)) for value in values if isinstance(value, str) and value]


def _handle_of(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("__handle__"), str):
        return value["__handle__"]
    return None


def _handle_arg(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict) and isinstance(value.get("__handle__"), str):
        return value
    if isinstance(value, str) and value.startswith("h:"):
        return {"__handle__": value}
    return None


class ResolveConverter(TimelineConverter):
    """Unified Project -> a Resolve execution plan.

    This is a plan, not a claim that the edit happened. Anything Resolve cannot
    express here (effects, transitions, subtitles, fades) is reported. Frame
    numbers are only produced when the project states its fps; guessing a rate
    would silently move every clip.
    """

    target = "resolve"

    def convert(self, project: Project) -> ConversionResult:
        unsupported: list[UnsupportedElement] = []
        warnings: list[str] = []
        fps = project.metadata.get("fps")
        if type(fps) not in (int, float) or not isfinite(fps) or fps <= 0:
            fps = None
            warnings.append("Sin 'fps' en metadata: el plan queda en segundos, sin frames.")

        assets: list[dict[str, Any]] = []
        for index, asset in enumerate(project.assets):
            if not asset.path:
                unsupported.append(
                    UnsupportedElement(
                        path=f"assets[{index}]",
                        kind="asset",
                        reason="El recurso no tiene ruta local.",
                        element_id=asset.id,
                    )
                )
                continue
            entry: dict[str, Any] = {
                "id": asset.id,
                "path": asset.path,
                "kind": asset.kind,
                "duration_seconds": asset.duration_seconds,
            }
            assets.append(entry)

        asset_ids = {asset["id"] for asset in assets}
        tracks: list[dict[str, Any]] = []
        for track_index, track in enumerate(project.tracks):
            if isinstance(track, SubtitleTrack):
                if track.cues:
                    unsupported.append(
                        UnsupportedElement(
                            path=f"tracks[{track_index}]",
                            kind="subtitles",
                            reason="El adaptador no crea subtítulos por el puente.",
                            element_id=track.id,
                        )
                    )
                continue
            clips: list[dict[str, Any]] = []
            if isinstance(track, VideoTrack):
                items = track.clips
                kind = "video"
            elif isinstance(track, AudioTrack):
                items = track.clips
                kind = "audio"
            else:  # pragma: no cover - the discriminated union has three members
                continue
            for clip in items:
                if clip.asset_id not in asset_ids:
                    unsupported.append(UnsupportedElement(
                        path=f"clips.{clip.id}", kind="clip",
                        reason="El clip no tiene un medio local exportable.", element_id=clip.id,
                    ))
                    continue
                entry = {
                    "id": clip.id,
                    "asset_id": clip.asset_id,
                    "start_seconds": clip.start_seconds,
                    "duration_seconds": clip.duration_seconds,
                    "source_in_seconds": clip.source_in_seconds,
                }
                if fps is not None:
                    entry["record_offset_frames"] = round(clip.start_seconds * fps)
                if clip.effects:
                    unsupported.append(
                        UnsupportedElement(
                            path=f"clips.{clip.id}.effects",
                            kind="effects",
                            reason="Los efectos no se convierten en esta fase.",
                            element_id=clip.id,
                        )
                    )
                if kind == "audio":
                    gain = getattr(clip, "gain_db", 0.0)
                    fade_in = getattr(clip, "fade_in_seconds", 0.0)
                    fade_out = getattr(clip, "fade_out_seconds", 0.0)
                    if gain or fade_in or fade_out:
                        unsupported.append(
                            UnsupportedElement(
                                path=f"clips.{clip.id}.audio",
                                kind="audio_processing",
                                reason="Ganancia y fundidos no se convierten en esta fase.",
                                element_id=clip.id,
                            )
                        )
                clips.append(entry)
            tracks.append({"id": track.id, "name": track.name, "kind": kind, "enabled": track.enabled,
                           "locked": track.locked, "clips": clips})

        for index, transition in enumerate(project.transitions):
            unsupported.append(
                UnsupportedElement(
                    path=f"transitions[{index}]",
                    kind="transition",
                    reason="Las transiciones no se convierten en esta fase.",
                    element_id=transition.id,
                )
            )
        for index, scene in enumerate(project.scenes):
            unsupported.append(
                UnsupportedElement(
                    path=f"scenes[{index}]",
                    kind="scene",
                    reason="Las escenas son metadatos del proyecto y no se exportan.",
                    element_id=scene.id,
                )
            )

        has_clip = any(track["clips"] for track in tracks)
        return ConversionResult(
            target=self.target,
            supported=has_clip,
            exported=["media import plan", "timeline plan", "clip plan"] if has_clip else [],
            unsupported=unsupported,
            warnings=warnings,
            payload={
                "fps": fps,
                "assets": assets,
                "tracks": tracks,
                "frame_based": fps is not None,
            },
        )


@register_adapter("davinci-resolve")
class ResolveAdapter(EditorAdapter):
    def __init__(
        self,
        plugin_id: str,
        config: dict[str, Any] | None = None,
        *,
        bridge: ResolveBridgeClient | None = None,
    ) -> None:
        super().__init__(plugin_id, config)
        self._bridge_instance = bridge
        self.last_health_error: str | None = None

    @property
    def bridge(self) -> ResolveBridgeClient:
        if self._bridge_instance is None:
            self._bridge_instance = ResolveBridgeClient()
        return self._bridge_instance

    # -- capabilities ------------------------------------------------------

    def get_capabilities(self) -> AdapterCapabilities:
        config = self._state_config()
        notes = [
            "DaVinci Resolve vía puente in-app autenticado (HMAC-SHA256, loopback).",
        ]
        edition = config.get("resolve_edition")
        if edition:
            notes.append(
                "Edición detectada: "
                + ("Studio" if edition == "studio" else "Free")
                + "."
            )
        if config.get("resolve_version"):
            notes.append(f"Versión: {config['resolve_version']}.")
        return AdapterCapabilities(
            operations=set(_IMPLEMENTED),
            capability_ids=_CAPABILITY_IDS,
            verified=bool(config.get("resolve_verified", False)),
            notes=notes,
        )

    # -- lifecycle ---------------------------------------------------------

    def health_check(self) -> bool:
        try:
            health = self.bridge.health()
        except (ResolveBridgeUnavailable, ResolveBridgeCallError) as exc:
            self.last_health_error = exc.message
            return False
        self.last_health_error = None
        self._remember_health(health)
        if health.get("connected") is True and health.get("current_project"):
            self._mark_verified(["project.inspect"])
        return health.get("connected") is True

    # -- media -------------------------------------------------------------

    def import_media(self, paths: list[str]) -> list[dict[str, Any]]:
        health = self._health()
        media_roots = _real_roots((health.get("policy") or {}).get("media_roots"))
        if not media_roots:
            raise InvalidOperation("El puente no publicó rutas de medios autorizadas.")
        resolved = [
            self._validated_path(value, media_roots, "medio", must_exist=True)
            for value in paths
        ]
        if not resolved:
            raise InvalidOperation("Indica al menos un archivo para importar.")
        imported = self.bridge.call("media_pool", "ImportMedia", resolved)
        if not isinstance(imported, list) or not imported:
            raise InvalidOperation("Resolve no confirmó la importación de medios.")
        media: list[dict[str, Any]] = []
        for item in imported:
            handle = _handle_of(item)
            if handle is None:
                continue
            name = self.bridge.call(handle, "GetName")
            properties = self.bridge.call(handle, "GetClipProperty")
            media.append(
                {
                    "handle": handle,
                    "name": name,
                    "file_path": (properties or {}).get("File Path") if isinstance(properties, dict) else None,
                    "duration": (properties or {}).get("Duration") if isinstance(properties, dict) else None,
                    "fps": (properties or {}).get("FPS") if isinstance(properties, dict) else None,
                }
            )
        actual = {_norm(item['file_path']) for item in media if item['file_path']}
        if actual != set(resolved):
            raise InvalidOperation("Resolve no confirmó todos los medios solicitados.")
        self._mark_verified(["media.import"])
        return media

    # -- timelines ---------------------------------------------------------

    def create_project(self, name: str, **options: Any) -> dict[str, Any]:
        if options or not isinstance(name, str) or not name.strip():
            raise InvalidOperation("Indica un nombre de proyecto sin opciones adicionales.")
        project = self.bridge.call("project_manager", "CreateProject", name.strip())
        handle = _handle_of(project)
        if handle is None or self.bridge.call(handle, "GetName") != name.strip():
            raise InvalidOperation("Resolve no confirmó la creación del proyecto.")
        self._mark_verified(["project.create"])
        return {"id": handle, "name": name.strip()}

    def create_timeline(self, project_id: str, name: str, **options: Any) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise InvalidOperation("La timeline necesita un nombre.")
        if options or not project_id.startswith("h:"):
            raise InvalidOperation("Indica el identificador del proyecto de Resolve, sin opciones adicionales.")
        pool = _handle_of(self.bridge.call(project_id, "GetMediaPool"))
        if pool is None:
            raise InvalidOperation("Resolve no devolvió el Media Pool del proyecto.")
        timeline = self.bridge.call(pool, "CreateEmptyTimeline", name.strip())
        handle = _handle_of(timeline)
        if handle is None:
            raise InvalidOperation("Resolve no devolvió una timeline utilizable.")
        current = self.bridge.call(project_id, "SetCurrentTimeline", timeline)
        self._mark_verified(["timeline.create"])
        return {
            "project_id": project_id,
            "name": name.strip(),
            "handle": handle,
            "current": current is True,
        }

    def add_track(self, timeline_id: str, track: dict[str, Any]) -> dict[str, Any]:
        track_type = track.get("type") or track.get("kind") or "video"
        if track_type not in {"video", "audio", "subtitle"}:
            raise InvalidOperation(f"Tipo de pista no soportado: '{track_type}'.")
        target = self._timeline_target(timeline_id)
        added = self.bridge.call(target, "AddTrack", track_type)
        if added is not True:
            raise InvalidOperation("Resolve no añadió la pista (AddTrack no devolvió True).")
        self._mark_verified(["track.add"])
        return {"timeline": timeline_id, "track_type": track_type, "added": True}

    def add_clip(self, timeline_id: str, clip: dict[str, Any]) -> dict[str, Any]:
        item = self._media_item(clip)
        info: dict[str, Any] = {"mediaPoolItem": item}
        for key, target_key in (("start_frame", "startFrame"), ("end_frame", "endFrame"), ("record_frame", "recordFrame")):
            value = clip.get(key)
            if value is not None:
                if type(value) is not int or value < 0:
                    raise InvalidOperation(f"'{key}' debe ser un entero no negativo.")
                info[target_key] = value
        if clip.get("track_index") is not None:
            index = clip["track_index"]
            if type(index) is not int or index < 1:
                raise InvalidOperation("'track_index' debe ser un entero mayor que cero.")
            info["trackIndex"] = index
        media_type = clip.get("media_type")
        if isinstance(media_type, str):
            if media_type not in _MEDIA_TYPES:
                raise InvalidOperation("'media_type' debe ser 'video' o 'audio'.")
            info["mediaType"] = _MEDIA_TYPES[media_type]
        elif type(media_type) is int and media_type in (1, 2):
            info["mediaType"] = media_type
        elif media_type is not None:
            raise InvalidOperation("'media_type' debe identificar vídeo o audio.")

        target = self._timeline_target(timeline_id)
        if target != "current_timeline" and self.bridge.call(
            "project", "SetCurrentTimeline", {"__handle__": target}
        ) is not True:
            raise InvalidOperation("Resolve no seleccionó la timeline solicitada.")
        envelope = self.bridge.call_encoded("media_pool", "AppendToTimeline", [info])
        value = envelope["value"]
        if value is False or value is None or value == []:
            raise InvalidOperation("Resolve no añadió el clip (AppendToTimeline no devolvió elementos).")
        if not isinstance(value, list):
            raise InvalidOperation("AppendToTimeline devolvió un valor inesperado.")
        self._mark_verified(["clip.add"])
        result: dict[str, Any] = {
            "timeline": timeline_id,
            "returned_items": len(value),
            "items": value,
        }
        if envelope.get("truncated"):
            result["truncated"] = envelope["truncated"]
        return result

    # -- render ------------------------------------------------------------

    def render_preview(self, timeline_id: str, **options: Any) -> dict[str, Any]:
        return self._render(timeline_id, options)

    def render_final(self, timeline_id: str, **options: Any) -> dict[str, Any]:
        return self._render(timeline_id, options)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        if not isinstance(job_id, str) or not job_id:
            raise InvalidOperation("Se necesita un id de trabajo de render.")
        status = self.bridge.call("project", "GetRenderJobStatus", job_id)
        if not isinstance(status, dict) or not status.get("JobStatus"):
            raise InvalidOperation("Resolve no devolvió el estado del trabajo de render.")
        self._mark_verified(["job.status"])
        if status["JobStatus"] in {"Complete", "Finalizado"} and status.get("CompletionPercentage") == 100:
            self._mark_verified(["render"])
        return status

    # -- internals ---------------------------------------------------------

    def _render(self, timeline_id: str, options: dict[str, Any]) -> dict[str, Any]:
        settings = options.get("settings") or options.get("render_settings")
        if not isinstance(settings, dict) or not settings:
            raise InvalidOperation(
                "Se requieren ajustes de render explícitos; el adaptador no inventa un preset."
            )
        health = self._health()
        output_roots = _real_roots((health.get("policy") or {}).get("output_roots"))
        if not output_roots:
            raise InvalidOperation("El puente no publicó rutas de salida autorizadas.")
        target_dir = settings.get("TargetDir")
        if not isinstance(target_dir, str) or not target_dir:
            raise InvalidOperation("Los ajustes de render necesitan 'TargetDir'.")
        settings = dict(settings)
        if set(settings) - {"TargetDir", "CustomName", "SelectAllFrames", "ExportVideo", "ExportAudio"}:
            raise InvalidOperation("Los ajustes de render contienen claves no admitidas.")
        name = settings.get("CustomName")
        if not isinstance(name, str) or not name or not all(c.isalnum() or c in "_-" for c in name):
            raise InvalidOperation("CustomName debe ser un nombre simple, sin ruta ni extensión.")
        for key in ("SelectAllFrames", "ExportVideo", "ExportAudio"):
            if key in settings and type(settings[key]) is not bool:
                raise InvalidOperation(f"'{key}' debe ser booleano.")
        settings["TargetDir"] = str(
            self._validated_path(target_dir, output_roots, "salida", must_exist=False)
        )
        destination = Path(settings["TargetDir"])
        if not destination.is_dir() or any(p.stem.casefold() == name.casefold() for p in destination.iterdir()):
            raise InvalidOperation("El directorio de salida debe existir y el nombre no puede reemplazar un archivo.")

        if timeline_id and timeline_id not in {"current", "current_timeline"}:
            handle = _handle_arg(timeline_id)
            if handle is not None:
                selected = self.bridge.call("project", "SetCurrentTimeline", handle)
                if selected is not True:
                    raise InvalidOperation("Resolve no seleccionó la timeline para el render.")
            else:
                self.bridge.named("set_current_timeline", {"timeline_name": timeline_id})

        configured = self.bridge.call("project", "SetRenderSettings", settings)
        if configured is not True:
            raise InvalidOperation("Resolve rechazó los ajustes de render.")
        job_id = self.bridge.call("project", "AddRenderJob")
        if not isinstance(job_id, str) or not job_id:
            raise InvalidOperation("Resolve no creó el trabajo de render (AddRenderJob).")
        started = self.bridge.call("project", "StartRendering", job_id)
        if started is not True:
            raise InvalidOperation("Resolve no confirmó el inicio del render.", details={"job_id": job_id})
        return {
            "job_id": job_id,
            "started": True,
            "timeline": timeline_id,
            "target_dir": settings["TargetDir"],
            "settings": settings,
        }

    def _health(self) -> dict[str, Any]:
        try:
            health = self.bridge.health()
        except (ResolveBridgeUnavailable, ResolveBridgeCallError) as exc:
            raise ResolveBridgeUnavailable(exc.message, details=exc.details) from exc
        self._remember_health(health)
        if health.get("connected") is not True:
            raise ResolveBridgeUnavailable("Resolve no confirmó una conexión activa.")
        return health

    def _timeline_target(self, timeline_id: str) -> str:
        if isinstance(timeline_id, str) and timeline_id.startswith("h:"):
            return timeline_id
        if timeline_id in {"current", "current_timeline"}:
            return "current_timeline"
        raise InvalidOperation("Indica un identificador de timeline de Resolve o 'current'.")

    def _media_item(self, clip: dict[str, Any]) -> dict[str, str]:
        explicit = _handle_arg(clip.get("media_handle"))
        if explicit is not None:
            return explicit
        path_value = clip.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise InvalidOperation(
                "El clip necesita 'media_handle' o 'path' para localizar el medio en Resolve."
            )
        media_roots = _real_roots((self._health().get("policy") or {}).get("media_roots"))
        if not media_roots:
            raise InvalidOperation("El puente no publicó rutas de medios autorizadas.")
        path = self._validated_path(path_value, media_roots, "medio", must_exist=True)

        root = self.bridge.call("media_pool", "GetRootFolder")
        root_handle = _handle_of(root)
        if root_handle is None:
            raise InvalidOperation("Resolve no devolvió la carpeta raíz del Media Pool.")
        pending: list[str] = [root_handle]
        seen: set[str] = set()
        while pending:
            folder = pending.pop()
            if folder in seen:
                continue
            seen.add(folder)
            clips = self.bridge.call(folder, "GetClipList") or []
            for item in clips:
                handle = _handle_of(item)
                if handle is None:
                    continue
                properties = self.bridge.call(handle, "GetClipProperty")
                if not isinstance(properties, dict):
                    continue
                file_path = properties.get("File Path")
                if isinstance(file_path, str) and file_path and _norm(file_path) == path:
                    return {"__handle__": handle}
            for subfolder in self.bridge.call(folder, "GetSubFolderList") or []:
                sub_handle = _handle_of(subfolder)
                if sub_handle is not None and sub_handle not in seen:
                    pending.append(sub_handle)
        raise InvalidOperation(
            "El medio no está en el Media Pool de Resolve; impórtalo antes de añadirlo.",
            details={"path": path},
        )

    @staticmethod
    def _validated_path(
        value: str, roots: list[str], label: str, *, must_exist: bool
    ) -> str:
        if not isinstance(value, str) or not value:
            raise InvalidOperation(f"La ruta de {label} debe ser una cadena no vacía.")
        if not Path(value).is_absolute() or ".." in Path(value).parts:
            raise InvalidOperation(f"La ruta de {label} debe ser absoluta y no contener '..'.")
        resolved = _norm(value)
        if not _under(resolved, roots):
            raise InvalidOperation(
                f"La ruta de {label} está fuera de las raíces autorizadas por el puente.",
                details={"path": value, "roots": roots},
            )
        if must_exist and not os.path.isfile(resolved):
            raise InvalidOperation(f"No existe el archivo de {label}: '{value}'.")
        return resolved

    def _state_config(self) -> dict[str, Any]:
        with Session(_engine()) as session:
            try:
                state = session.get(PluginState, self.plugin_id)
            except OperationalError:
                state = None
            return dict(state.config) if state is not None else {}

    def _remember_health(self, health: dict[str, Any]) -> None:
        try:
            with Session(_engine()) as session:
                state = session.get(PluginState, self.plugin_id)
                if state is None:
                    return
                config = dict(state.config)
                for key, source in (
                    ("resolve_edition", "edition"),
                    ("resolve_version", "version"),
                    ("resolve_product", "product"),
                ):
                    value = health.get(source)
                    if isinstance(value, str) and value:
                        config[key] = value
                state.config = config
                session.add(state)
                session.commit()
        except OperationalError:
            return

    def _mark_verified(self, capabilities: list[str]) -> None:
        try:
            with Session(_engine()) as session:
                state = session.get(PluginState, self.plugin_id)
                if state is None:
                    return
                config = dict(state.config)
                config["resolve_verified"] = True
                config["verified_capabilities"] = sorted(
                    set(config.get("verified_capabilities", [])) | set(capabilities)
                )
                state.config = config
                session.add(state)
                session.commit()
        except OperationalError:
            return
