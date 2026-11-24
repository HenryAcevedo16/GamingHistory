"""VectCutAPI's local HTTP draft workflow (no MCP, cloud preview or render)."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path
from tempfile import mkdtemp
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlmodel import Session

from app.core import db
from app.core.config import settings
from app.core.errors import CapabilityNotAvailable, InvalidOperation, StudioError
from app.core.exec import run_command
from app.editing.adapter import AdapterCapabilities, EditorAdapter, EditorOperation
from app.editing.converters import ConversionResult, TimelineConverter, UnsupportedElement
from app.editing.drafts import DraftResult, require_draft
from app.editing.persistence import ProjectRepository
from app.editing.registry import register_adapter
from app.editing.timeline import Project
from app.models.audit import AuditLog
from app.models.plugin import PluginState
from app.plugins.diagnostics import expand_target
from app.plugins.registry import load_registry

_ID = re.compile(r"dfd_cat_[0-9]+_[0-9a-f]{8}")
_FORMATS = {"video": (".mp4", "mov"), "audio": (".mp3", "mp3")}
_CALLS = {
    ("GET", "/get_font_types"), ("POST", "/create_draft"), ("POST", "/add_video"),
    ("POST", "/add_audio"), ("POST", "/add_subtitle"), ("POST", "/save_draft"),
}
_ARTIFACT_CAPS = {"draft.create", "draft.save", "draft.export_capcut"}
_ITEM_CAPS = {"video": "clip.add", "audio": "audio.add", "text": "subtitle.add"}
_STATE_LOCK = Lock()


class VectCutError(StudioError):
    code = "VECTCUT_FAILED"
    status_code = 502


class VectCutUnavailable(VectCutError):
    code = "VECTCUT_UNAVAILABLE"
    status_code = 503


def _inside(root: Path, path: Path) -> Path:
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or resolved == root:
            raise ValueError
    except (ValueError, OSError, RuntimeError) as exc:
        raise InvalidOperation("Ruta fuera del directorio autorizado.") from exc
    return resolved


def _media_path(value: str, kind: str) -> Path:
    raw = Path(value)
    if (not value or ".." in raw.parts or value.startswith(("//", "\\\\"))
            or ":" in str(Path(*raw.parts[1:] if raw.anchor else raw.parts))
            or any(c in value for c in "\0\r\n") or raw.suffix.lower() != _FORMATS[kind][0]):
        raise InvalidOperation("Se requiere un MP4 de vídeo o MP3 de audio local dentro del workspace.")
    root = settings.resolved_workspace_dir
    path = _inside(root, root / raw)
    if not path.is_file():
        raise InvalidOperation("No existe el archivo de medio local.")
    return path


def _us(seconds: float) -> int:
    if not math.isfinite(seconds) or not 0 <= seconds < 360_000:
        raise InvalidOperation("Tiempo fuera del rango admitido para el borrador.")
    return round(seconds * 1_000_000)


def _srt_clock(us: int) -> str:
    seconds, ms = divmod(us // 1000, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


class VectCutConverter(TimelineConverter):
    target = "capcut"

    def convert(self, project: Project) -> ConversionResult:
        result = ConversionResult(target=self.target, supported=False)
        assets = {asset.id: asset for asset in project.assets}
        items: list[dict[str, Any]] = []

        def unsupported(path: str, kind: str, element_id: str, reason: str) -> None:
            result.unsupported.append(UnsupportedElement(
                path=path, kind=kind, element_id=element_id, reason=reason,
            ))

        for index, track in enumerate(project.tracks):
            prefix = f"tracks.{index}"
            if not track.enabled:
                unsupported(prefix, "track", track.id, "Pista desactivada; se omite.")
                continue
            if track.locked:
                unsupported(prefix, "track_lock", track.id, "No se conserva el bloqueo de pista.")
            name = f"ghs_{track.kind}_{index + 1}"
            if track.kind == "subtitle":
                if not track.cues:
                    unsupported(prefix, "track", track.id, "La API crea pistas al insertar elementos.")
                for cue in sorted(track.cues, key=lambda cue: cue.start_seconds):
                    start = _us(cue.start_seconds) // 1000 * 1000
                    end = _us(cue.start_seconds + cue.duration_seconds) // 1000 * 1000
                    lines = cue.text.splitlines()
                    if (end <= start or not lines or any(not line.strip() for line in lines)
                            or len(cue.text) > 4096 or "\0" in cue.text):
                        unsupported(prefix, "subtitle", cue.id, "Texto o duración no representable en SRT.")
                        continue
                    if cue.style or cue.language:
                        unsupported(prefix, "subtitle_metadata", cue.id, "Solo se exportan texto y tiempos.")
                    text = "\n".join(line.strip() for line in lines)
                    items.append(dict(kind="text", track=name, start=start, length=end-start, text=text))
                    result.exported.append(cue.id)
                continue
            if not track.clips:
                unsupported(prefix, "track", track.id, "La API crea pistas al insertar elementos.")
            for clip in sorted(track.clips, key=lambda clip: clip.start_seconds):
                asset = assets[clip.asset_id]
                if asset.kind != track.kind or not asset.path or Path(asset.path).suffix.lower() != _FORMATS[track.kind][0]:
                    unsupported(prefix, "clip", clip.id, "Solo vídeo MP4 y audio MP3 locales.")
                    continue
                duration = _us(clip.duration_seconds)
                if not duration:
                    unsupported(prefix, "clip", clip.id, "Duración inferior a la precisión del borrador.")
                    continue
                volume = 1.0
                if track.kind == "audio":
                    if clip.fade_in_seconds or clip.fade_out_seconds:
                        unsupported(prefix, "audio_fade", clip.id, "No se exportan fundidos.")
                    if not math.isfinite(clip.gain_db) or clip.gain_db > 0:
                        unsupported(prefix, "audio_gain", clip.id, "Solo se conserva ganancia de hasta 0 dB.")
                    else:
                        volume = 10 ** (clip.gain_db / 20)
                for effect in clip.effects:
                    unsupported(prefix, "effect", effect.id, "No se exportan efectos.")
                items.append(dict(kind=track.kind, track=name, path=asset.path, start=_us(clip.start_seconds),
                                  length=duration, source=_us(clip.source_in_seconds), volume=volume,
                                  index=index))
                result.exported.append(clip.id)
        for index, transition in enumerate(project.transitions):
            unsupported(f"transitions.{index}", "transition", transition.id, "No se exportan transiciones.")
        result.supported = bool(items)
        result.payload = {"items": items}
        return result


def draft_sources(converted: ConversionResult) -> dict[tuple[str, str], Path]:
    return {(item["kind"], item["path"]): _media_path(item["path"], item["kind"])
            for item in (converted.payload or {}).get("items", []) if item["kind"] != "text"}


@register_adapter("vectcut-capcut")
class VectCutAdapter(EditorAdapter):
    def _audit(self, action: str, status: str, detail: str = "") -> None:
        with Session(db.engine) as session:
            session.add(AuditLog(plugin_id=self.plugin_id, action=action, status=status, detail=detail))
            session.commit()

    def _endpoint(self) -> str:
        manifest = load_registry(settings.resolved_plugins_dir).manifests.get(self.plugin_id)
        raw = expand_target(manifest.mcp_command_or_endpoint or "") if manifest else ""
        try:
            url = urlsplit(raw)
            if (url.scheme != "http" or url.username is not None or url.password is not None
                    or url.path not in ("", "/") or url.query or url.fragment or url.port is None
                    or any(c.isspace() for c in raw) or "\\" in raw or "?" in raw or "#" in raw):
                raise ValueError
            host = ipaddress.ip_address("127.0.0.1" if url.hostname == "localhost" else url.hostname or "")
            if not host.is_loopback or not url.port:
                raise ValueError
        except ValueError as exc:
            raise InvalidOperation("VECTCUT_ENDPOINT debe ser un origen HTTP de loopback con puerto.") from exc
        return f"http://{'[' + str(host) + ']' if host.version == 6 else host}:{url.port}"

    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if (method, path) not in _CALLS:
            self._audit("vectcut.http", "denied", "endpoint_not_allowed")
            raise CapabilityNotAvailable("vectcut.http", plugin_id=self.plugin_id)
        try:
            origin = self._endpoint()
        except InvalidOperation:
            self._audit("vectcut.http", "denied", "invalid_endpoint")
            raise
        action = f"vectcut.http{path}"
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
                response = client.request(method, origin + path, json=payload,
                                          timeout=90 if path == "/save_draft" else 5)
                response.raise_for_status()
                body = response.json()
            if not isinstance(body, dict) or body.get("success") is not True or "output" not in body:
                raise ValueError
        except httpx.RequestError as exc:
            self._audit(action, "error", "transport")
            raise VectCutUnavailable("Sin respuesta utilizable de VectCutAPI (conexión o timeout).") from exc
        except (httpx.HTTPStatusError, ValueError) as exc:
            self._audit(action, "error", "invalid_response")
            raise VectCutError(f"VectCutAPI rechazó {path} o devolvió una respuesta incompatible.") from exc
        self._audit(action, "ok")
        return body["output"]

    def _require_local_profile(self) -> None:
        # This is the operator's trusted checkout running the HTTP service. The HTTP
        # API does not expose the process's effective upload/profile configuration.
        folder = os.environ.get("VECTCUT_ROOT")
        try:
            if not folder or not Path(folder).is_absolute():
                raise ValueError
            root = Path(folder).resolve(strict=True)
            if not (root / "capcut_server.py").is_file() or not (root / "settings" / "local.py").is_file():
                raise ValueError
            config = root / "config.json"
            try:
                cfg = json.loads(config.read_text(encoding="utf-8-sig"))
            except FileNotFoundError:
                cfg = {}  # The reviewed CapCut checkout defaults to local, upload off.
            if (not isinstance(cfg, dict) or cfg.get("is_upload_draft", False) is not False
                    or cfg.get("is_capcut_env", True) is not True
                    or cfg.get("draft_profile", "capcut_legacy") not in ("capcut", "capcut_legacy")
                    or cfg.get("oss_config") or cfg.get("mp4_oss_config")):
                raise ValueError
        except (ValueError, OSError, RuntimeError) as exc:
            self._audit("vectcut.local_profile", "denied", "unsafe_or_unconfirmed_profile")
            raise InvalidOperation(
                "Configura VECTCUT_ROOT con el checkout local en ejecución, perfil CapCut y subida desactivada."
            ) from exc

    def health_check(self) -> bool:
        try:
            fonts = self._call("GET", "/get_font_types")
            if not isinstance(fonts, list) or not any(
                isinstance(font, dict) and font.get("name") == "思源粗宋" for font in fonts
            ):
                raise VectCutError("El servicio no expone el catálogo de fuentes esperado.")
            self._require_local_profile()
        except StudioError as exc:
            self.last_health_error = exc.message
            return False
        return True

    def get_capabilities(self) -> AdapterCapabilities:
        effective = _ARTIFACT_CAPS | set(_ITEM_CAPS.values())
        with Session(db.engine) as session:
            state = session.get(PluginState, self.plugin_id)
            verified = (set(state.config.get("verified_capabilities", [])) if state else set()) & effective
        return AdapterCapabilities(
            operations={EditorOperation.HEALTH_CHECK, EditorOperation.EXPORT_PROJECT},
            capability_ids=effective, verified=bool(verified),
            notes=["Genera borradores editables; no genera renders. El render final se hace manualmente en CapCut.",
                   "Las actualizaciones de CapCut pueden cambiar el formato y romper la apertura del borrador."],
        )

    @staticmethod
    def _stage(path: Path, kind: str, run_dir: Path, index: int) -> Path:
        suffix, demuxer = _FORMATS[kind]
        dest = run_dir / f"media-{index}{suffix}"
        streams = ["-map", "0:v:0", "-map", "0:a:0?"] if kind == "video" else ["-map", "0:a:0"]
        # Give the upstream probe a fresh standalone file, never the input container
        # or a URL supplied by the caller. No external references or playlists.
        result = run_command("ffmpeg", ["-nostdin", "-v", "error", "-n", "-protocol_whitelist", "file",
                                       "-f", demuxer, "-i", str(path), *streams,
                                       "-map_metadata", "-1", "-map_chapters", "-1", "-c", "copy", str(dest)],
                             allowed_binaries={"ffmpeg"}, timeout=60)
        if not result.ok or not dest.is_file() or not dest.stat().st_size:
            raise InvalidOperation("FFmpeg no pudo preparar el archivo local para VectCutAPI.")
        return dest

    @staticmethod
    def _verify(draft: Path, items: list[dict[str, Any]], width: int, height: int) -> None:
        try:
            info = _inside(draft, draft / "draft_info.json")
            content = json.loads(info.read_text(encoding="utf-8-sig"))
            if (content["canvas_config"]["width"], content["canvas_config"]["height"]) != (width, height):
                raise ValueError
            by_track: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in items:
                by_track[item["track"]].append(item)
            tracks = {track["name"]: track for track in content["tracks"]}
            for name, expected in by_track.items():
                track = tracks[name]
                segments = track["segments"]
                kind = expected[0]["kind"]
                if len(segments) != len(expected) or track["type"] != kind:
                    raise ValueError
                materials = {material["id"]: material for material in content["materials"][kind + "s"]}
                for item, segment in zip(expected, segments):
                    target = segment["target_timerange"]
                    if (target["start"], target["duration"]) != (item["start"], item["length"]):
                        raise ValueError
                    material = materials[segment["material_id"]]
                    if kind == "text":
                        if json.loads(material["content"])["text"] != item["text"]:
                            raise ValueError
                    else:
                        source = segment["source_timerange"]
                        if (source["start"], source["duration"]) != (item["source"], item["length"]):
                            raise ValueError
                        expected_path = item["staged"]
                        media = _inside(draft, Path(material["path"]))
                        if (Path(material["remote_url"]) != expected_path or not media.is_file()
                                or media.stat().st_size != expected_path.stat().st_size):
                            raise ValueError
                        if not math.isclose(segment["volume"], item["volume"], abs_tol=1e-6):
                            raise ValueError
        except (OSError, ValueError, TypeError, KeyError, AttributeError, InvalidOperation) as exc:
            raise VectCutError("El borrador en disco no contiene los medios, tiempos o subtítulos esperados.") from exc

    @staticmethod
    def _local_metadata(draft: Path, *, final_path: Path, duration_us: int | None = None) -> None:
        meta_path = _inside(draft, draft / "draft_meta_info.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        if not isinstance(meta, dict):
            raise VectCutError("Metadatos de borrador incompatibles.")
        # The upstream template contains its author's paths, a fixed ID and
        # cloud sync enabled. Generated artifacts must be distinct and local.
        meta.update(cloud_draft_cover=False, cloud_draft_sync=False, draft_name=final_path.name,
                    draft_fold_path=final_path.as_posix(), draft_root_path=final_path.parent.as_posix())
        if duration_us is not None:
            now = time.time_ns() // 1000
            meta.update(draft_id=str(uuid4()).upper(), tm_draft_create=now,
                        tm_draft_modified=now, tm_duration=duration_us)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def export_project(self, timeline_id: str, target: str, *, width: int = 1920, height: int = 1080,
                       draft_id: str | None = None, revision: str | None = None) -> dict[str, Any]:
        action = "vectcut.export_project"
        try:
            if target == "capcut-desktop" and draft_id is not None:
                response = self._deploy(timeline_id, draft_id)
            elif target == "capcut" and draft_id is None:
                response = self._generate(timeline_id, width, height, revision)
            else:
                raise CapabilityNotAvailable("draft.export", plugin_id=self.plugin_id)
        except (InvalidOperation, CapabilityNotAvailable):
            self._audit(action, "denied", "operation_or_input_rejected")
            raise
        except VectCutError:
            self._audit(action, "error", "draft_failed")
            raise
        except (OSError, ValueError) as exc:
            self._audit(action, "error", "filesystem")
            raise VectCutError("No se pudo completar la operación del borrador en disco.") from exc
        self._audit(action, "ok")
        return response

    def _generate(self, project_id: str, width: int, height: int, revision: str | None) -> dict[str, Any]:
        from app.editing.revision import check_revision

        if any(type(n) is not int or not 16 <= n <= 7680 for n in (width, height)):
            raise InvalidOperation("Dimensiones del borrador fuera de rango.")
        self._require_local_profile()
        with Session(db.engine) as session:
            project = ProjectRepository(session).get(project_id)
        check_revision(project, revision)
        converted = VectCutConverter().convert(project)
        items = (converted.payload or {}).get("items", [])
        if not converted.supported:
            raise InvalidOperation("El timeline no contiene elementos exportables.",
                                   details=[item.model_dump() for item in converted.unsupported])
        sources = draft_sources(converted)
        # Reject out-of-workspace media before the first HTTP call.
        try:
            self._endpoint()
        except InvalidOperation:
            self._audit("vectcut.http", "denied", "invalid_endpoint")
            raise
        run_dir = Path(mkdtemp(prefix="vectcut-", dir=settings.resolved_workspace_dir))
        staged = {key: self._stage(path, key[0], run_dir, n)
                  for n, (key, path) in enumerate(sources.items())}
        output = self._call("POST", "/create_draft", {"width": width, "height": height})
        draft_id = output.get("draft_id") if isinstance(output, dict) else None
        if not isinstance(draft_id, str) or not _ID.fullmatch(draft_id):
            raise VectCutError("VectCutAPI devolvió un identificador de borrador incompatible.")
        draft = run_dir / draft_id
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            kind = item["kind"]
            if kind == "text":
                groups[item["track"]].append(item)
                continue
            item["staged"] = staged[kind, item["path"]]
            payload = {"draft_id": draft_id, "track_name": item["track"], f"{kind}_url": str(item["staged"]),
                       "start": item["source"]/1e6, "end": (item["source"]+item["length"])/1e6,
                       "target_start": item["start"]/1e6, "volume": item["volume"]}
            if kind == "video":
                payload["relative_index"] = item["index"]
            self._insert(f"/add_{kind}", payload, draft_id)
        for name, cues in groups.items():
            srt = "\n\n".join(f"{n}\n{_srt_clock(cue['start'])} --> "
                              f"{_srt_clock(cue['start'] + cue['length'])}\n{cue['text']}"
                              for n, cue in enumerate(cues, 1)) + "\n"
            self._insert("/add_subtitle", {"draft_id": draft_id, "track_name": name, "srt": srt}, draft_id)
        self._require_local_profile()
        saved = self._call("POST", "/save_draft", {"draft_id": draft_id, "draft_folder": str(run_dir),
                                                  "auto_deploy": False, "auto_reload": False})
        if (not isinstance(saved, dict) or saved.get("success") is not True
                or not isinstance(saved.get("draft_url"), str) or Path(saved["draft_url"]) != draft
                or _inside(run_dir, draft) != draft):
            raise VectCutError("VectCutAPI no devolvió la ruta local esperada.")
        self._verify(draft, items, width, height)
        self._local_metadata(draft, final_path=draft,
                             duration_us=max(item["start"] + item["length"] for item in items))
        result = DraftResult(id=draft_id, project_id=project_id, plugin_id=self.plugin_id, path=str(draft))
        with _STATE_LOCK, Session(db.engine) as session:
            state = session.get(PluginState, self.plugin_id) or PluginState(plugin_id=self.plugin_id)
            verified = _ARTIFACT_CAPS | {_ITEM_CAPS[item["kind"]] for item in items}
            state.config = {**state.config, "verified_capabilities": sorted(
                verified | set(state.config.get("verified_capabilities", []))
            )}
            session.add(state)
            session.add(result)
            session.commit()
            session.refresh(result)
        return {"draft": result.model_dump(), "exported": converted.exported,
                "unsupported": [item.model_dump() for item in converted.unsupported]}

    def _insert(self, path: str, payload: dict[str, Any], draft_id: str) -> None:
        output = self._call("POST", path, payload)
        if not isinstance(output, dict) or output.get("draft_id") != draft_id:
            raise VectCutError("VectCutAPI respondió con un borrador distinto al solicitado.")

    def _deploy(self, project_id: str, draft_id: str) -> dict[str, Any]:
        with Session(db.engine) as session:
            result = require_draft(session, project_id, draft_id, self.plugin_id)
        source = _inside(settings.resolved_workspace_dir, Path(result.path))
        configured = os.environ.get("CAPCUT_DRAFTS_DIR") or self._configured_drafts_dir()
        if not configured or not Path(configured).is_absolute() or configured.startswith(("//", "\\\\")):
            raise InvalidOperation("Confirma la carpeta local de CapCut en Global Settings y configura CAPCUT_DRAFTS_DIR.")
        root = Path(configured).resolve(strict=True)
        if (not root.is_dir() or root == Path(root.anchor) or source == root or root.is_relative_to(source)
                or any(part.lower().startswith("com.lveditor.cloud.draft") for part in root.parts)
                or source.name != draft_id or not _ID.fullmatch(draft_id) or not (source / "draft_info.json").is_file()):
            raise InvalidOperation("Origen o carpeta de borradores de CapCut inválidos.")
        dest = root / draft_id
        if dest.exists() or dest.is_symlink():
            raise InvalidOperation("Ya existe un borrador en CapCut con ese identificador.", status_code=409)
        for path in source.rglob("*"):
            if path.is_symlink() or _inside(source, path) != path:
                raise InvalidOperation("No se copian enlaces de un borrador.")
        shutil.copytree(source, dest)
        self._local_metadata(dest, final_path=dest)
        return {"draft_id": draft_id, "path": str(dest)}

    @staticmethod
    def _configured_drafts_dir() -> str | None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return None
        candidate = Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        try:
            meta = json.loads((candidate / "root_meta_info.json").read_text(encoding="utf-8-sig"))
            if isinstance(meta, dict) and Path(meta["root_path"]) == candidate:
                return str(candidate)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return None
