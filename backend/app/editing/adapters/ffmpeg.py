"""Local FFmpeg adapter with explicit workspace and conversion limits."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from sqlmodel import Session
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.errors import CapabilityNotAvailable, InvalidOperation
from app.core.exec import run_command
from app.core.db import engine
from app.editing.adapter import AdapterCapabilities, EditorAdapter, EditorOperation
from app.editing.converters import ConversionResult, UnsupportedElement
from app.editing.jobs import JobRepository
from app.editing.media_formats import FORMATS, IMAGE_EXTENSIONS
from app.editing.registry import register_adapter
from app.editing.timeline import Asset, AudioTrack, Project, SubtitleTrack, VideoTrack
from app.models.plugin import PluginState

_BINARIES = {"ffmpeg", "ffprobe"}
_IMPLEMENTED = {
    EditorOperation.IMPORT_MEDIA,
    EditorOperation.CREATE_TIMELINE,
    EditorOperation.RENDER_PREVIEW,
    EditorOperation.RENDER_FINAL,
    EditorOperation.EXPORT_PROJECT,
    EditorOperation.GET_JOB_STATUS,
}


def workspace_path(value: str | Path) -> Path:
    """Resolve only paths within the configured workspace, rejecting traversal."""
    raw = Path(value)
    if ".." in raw.parts:
        raise InvalidOperation("Las rutas con '..' no están permitidas.")
    root = settings.resolved_workspace_dir
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InvalidOperation(
            "La ruta debe estar dentro del directorio de trabajo autorizado.",
            details={"workspace": str(root), "path": str(value)},
        ) from exc
    return resolved


class FFmpegConverter:
    target = "ffmpeg"

    @staticmethod
    def _streams(asset: Asset) -> list[dict[str, Any]]:
        streams = asset.metadata.get("streams") or []
        return [stream for stream in streams if isinstance(stream, dict)]

    def _has_audio(self, asset: Asset) -> bool:
        return any(stream.get("codec_type") == "audio" for stream in self._streams(asset))

    def _target_size(self, assets: dict[str, Asset], clips: list[Any]) -> tuple[int, int]:
        for clip in clips:
            for stream in self._streams(assets[clip.asset_id]):
                if stream.get("codec_type") == "video" and stream.get("width") and stream.get("height"):
                    return int(stream["width"]), int(stream["height"])
        return 1280, 720

    def _target_fps(self, assets: dict[str, Asset], clips: list[Any]) -> float:
        for clip in clips:
            for stream in self._streams(assets[clip.asset_id]):
                if stream.get("codec_type") != "video":
                    continue
                for key in ("avg_frame_rate", "r_frame_rate"):
                    value = str(stream.get(key) or "")
                    if "/" in value:
                        numerator, _, denominator = value.partition("/")
                        try:
                            if float(denominator) > 0:
                                return float(numerator) / float(denominator)
                        except ValueError:
                            continue
        return 25.0

    def convert(self, project: Project) -> ConversionResult:
        unsupported: list[UnsupportedElement] = []
        assets = {asset.id: asset for asset in project.assets}
        video_tracks = [track for track in project.tracks if isinstance(track, VideoTrack) and track.enabled and track.clips]
        video_clips = sorted(
            [clip for track in video_tracks[:1] for clip in track.clips],
            key=lambda clip: clip.start_seconds,
        )
        audio_clips = sorted(
            [clip for track in project.tracks if isinstance(track, AudioTrack) and track.enabled for clip in track.clips],
            key=lambda clip: clip.start_seconds,
        )
        for index, transition in enumerate(project.transitions):
            unsupported.append(UnsupportedElement(path=f"transitions[{index}]", kind="transition", reason="Las transiciones no se exportan en Fase 3.", element_id=transition.id))
        for track_index, track in enumerate(project.tracks):
            if not track.enabled and (getattr(track, "clips", []) or getattr(track, "cues", [])):
                unsupported.append(UnsupportedElement(path=f"tracks[{track_index}]", kind="track", reason="Pista desactivada; se omite.", element_id=track.id))
                continue
            if isinstance(track, SubtitleTrack) and track.cues:
                unsupported.append(UnsupportedElement(path=f"tracks[{track_index}]", kind="subtitles", reason="Los subtítulos no se exportan en Fase 3.", element_id=track.id))
        for track in video_tracks[1:]:
            unsupported.append(UnsupportedElement(path=f"tracks.{track.id}", kind="video_track", reason="Solo se exporta una pista de vídeo secuencial; las capas superiores no se aplanan en Fase 3.", element_id=track.id))
        previous_end = 0.0
        for clip in video_clips:
            if clip.start_seconds > previous_end + 1e-6:
                unsupported.append(UnsupportedElement(path=f"clips.{clip.id}", kind="timeline_gap", reason="Los huecos sin clip no se rellenan en Fase 3.", element_id=clip.id))
            previous_end = max(previous_end, clip.start_seconds + clip.duration_seconds)
        inputs: list[str] = []
        filters: list[str] = []
        input_index = 0
        segment_labels: list[str] = []
        target_size = self._target_size(assets, video_clips)
        target_fps = self._target_fps(assets, video_clips)
        for clip in video_clips:
            asset = assets[clip.asset_id]
            if not asset.path:
                unsupported.append(UnsupportedElement(path=f"assets.{asset.id}", kind="asset", reason="El recurso no tiene ruta local.", element_id=asset.id))
                continue
            source = workspace_path(asset.path)
            streams = self._streams(asset)
            if not source.is_file():
                unsupported.append(UnsupportedElement(path=f"assets.{asset.id}", kind="asset", reason="El archivo local no existe.", element_id=asset.id))
                continue
            if streams and not any(stream.get("codec_type") == "video" for stream in streams):
                unsupported.append(UnsupportedElement(path=f"clips.{clip.id}", kind="clip", reason="El recurso no tiene pista de vídeo.", element_id=clip.id))
                continue
            if clip.effects:
                unsupported.append(UnsupportedElement(path=f"clips.{clip.id}.effects", kind="effects", reason="Los efectos no se exportan en Fase 3.", element_id=clip.id))
            width, height = target_size
            if asset.kind == "image":
                inputs += ["-protocol_whitelist", "file", "-loop", "1", "-pattern_type", "none", "-f", "image2"]
            elif demuxer := FORMATS.get(source.suffix.lower()):
                inputs += ["-protocol_whitelist", "file", "-format_whitelist", demuxer]
            inputs += ["-ss", f"{clip.source_in_seconds:g}", "-t", f"{clip.duration_seconds:g}", "-i", str(source)]
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"fps={target_fps:g}[v{input_index}]"
            )
            if self._has_audio(asset):
                filters.append(
                    f"[{input_index}:a]asetpts=PTS-STARTPTS,"
                    f"aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{input_index}]"
                )
            else:
                filters.append(
                    f"anullsrc=r=44100:cl=stereo,atrim=0:{clip.duration_seconds:g},"
                    f"asetpts=PTS-STARTPTS[a{input_index}]"
                )
            segment_labels.append(f"[v{input_index}][a{input_index}]")
            input_index += 1
        if not segment_labels:
            return ConversionResult(target=self.target, supported=False, unsupported=unsupported, warnings=["No hay clips de vídeo exportables."])
        filters.append("".join(segment_labels) + f"concat=n={len(segment_labels)}:v=1:a=1[vout][aseq]")
        mix_labels = ["[aseq]"]
        for clip in audio_clips:
            asset = assets[clip.asset_id]
            if not asset.path:
                unsupported.append(UnsupportedElement(path=f"assets.{asset.id}", kind="asset", reason="El recurso no tiene ruta local.", element_id=asset.id))
                continue
            source = workspace_path(asset.path)
            if not source.is_file() or (self._streams(asset) and not self._has_audio(asset)):
                unsupported.append(UnsupportedElement(path=f"audio.{clip.id}", kind="clip", reason="El recurso local no existe o no contiene audio.", element_id=clip.id))
                continue
            if clip.effects:
                unsupported.append(UnsupportedElement(path=f"audio.{clip.id}.effects", kind="effects", reason="Los efectos de audio no se exportan en Fase 3.", element_id=clip.id))
            if clip.fade_in_seconds or clip.fade_out_seconds:
                unsupported.append(UnsupportedElement(path=f"audio.{clip.id}.fades", kind="audio_fade", reason="Los fundidos de audio no se exportan en Fase 3.", element_id=clip.id))
            if demuxer := FORMATS.get(source.suffix.lower()):
                inputs += ["-protocol_whitelist", "file", "-format_whitelist", demuxer]
            inputs += ["-ss", f"{clip.source_in_seconds:g}", "-t", f"{clip.duration_seconds:g}", "-i", str(source)]
            delay = round(clip.start_seconds * 1000)
            filters.append(f"[{input_index}:a]asetpts=PTS-STARTPTS,volume={10 ** (clip.gain_db / 20):.8f},adelay={delay}:all=1[am{input_index}]")
            mix_labels.append(f"[am{input_index}]")
            input_index += 1
        audio_output = "[aseq]"
        if len(mix_labels) > 1:
            filters.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=longest[aout]")
            audio_output = "[aout]"
        return ConversionResult(
            target=self.target,
            supported=True,
            exported=["video cuts", "video concat", "audio mix"],
            unsupported=unsupported,
            payload={"args": [*inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", audio_output, "-c:v", "libx264", "-c:a", "aac"]},
        )


@register_adapter("ffmpeg")
class FFmpegAdapter(EditorAdapter):
    def get_capabilities(self) -> AdapterCapabilities:
        with Session(engine) as session:
            try:
                state = session.get(PluginState, self.plugin_id)
            except OperationalError:
                state = None
            verified = bool((state.config if state else {}).get("ffmpeg_verified", False))
        return AdapterCapabilities(operations=_IMPLEMENTED, verified=verified, notes=["FFmpeg local: corte, unión y mezcla con recodificación."])

    def import_media(self, paths: list[str]) -> list[dict[str, Any]]:
        media: list[dict[str, Any]] = []
        for value in paths:
            path = workspace_path(value)
            if not path.is_file():
                raise InvalidOperation(f"No existe el medio local '{path}'.")
            suffix = path.suffix.lower()
            expected = FORMATS.get(suffix)
            # No playlists/network protocols. Image pipe formats inspect only this file,
            # not sequences inferred from its name.
            allowlist = expected or ",".join(sorted(set(FORMATS.values())))
            result = run_command("ffprobe", ["-v", "error", "-protocol_whitelist", "file",
                                 "-format_whitelist", allowlist, "-show_entries",
                                 "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate:stream_disposition=attached_pic",
                                 "-of", "json", str(path)], timeout=settings.command_timeout_seconds,
                                 allowed_binaries=_BINARIES, cwd=settings.resolved_workspace_dir)
            if not result.ok:
                reason = (result.error or result.stderr).strip().splitlines()[-1:]
                raise InvalidOperation(f"ffprobe falló: {' '.join(reason)[:300] or 'medio inválido'}.",
                                       code="MEDIA_PROBE_FAILED")
            payload = json.loads(result.stdout)
            streams = payload.get("streams", [])
            video = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
            audio = [s for s in streams if s.get("codec_type") == "audio"]
            try:
                duration = float(payload.get("format", {}).get("duration", 0))
            except ValueError:
                duration = 0
            image = suffix in IMAGE_EXTENSIONS
            if (result.stderr.strip() or not (video or audio) or
                (image and not any(s.get("width") and s.get("height") for s in video)) or
                (not image and (not math.isfinite(duration) or duration <= 0))):
                raise InvalidOperation("ffprobe no encontró un medio válido con imagen o duración utilizable.",
                                       code="MEDIA_PROBE_FAILED")
            kind = "image" if image else "video" if video else "audio"
            media.append({"path": str(path), "kind": kind, "duration_seconds": 0 if image else duration, "streams": streams})
        self._mark_verified(["media.inspect"])
        return media

    def create_timeline(self, project_id: str, name: str, **options: Any) -> dict[str, Any]:
        from app.editing.persistence import ProjectRepository

        with Session(engine) as session:
            project = ProjectRepository(session).get(project_id)
        return {
            "project_id": project.id,
            "name": name,
            "target": "ffmpeg",
            "assets": len(project.assets),
            "tracks": len(project.tracks),
            "clips": sum(len(getattr(track, "clips", [])) for track in project.tracks),
        }

    def render_preview(self, timeline_id: str, **options: Any) -> Any:
        return self._render(options["project"], options["output_path"], options.get("overwrite", False))

    def render_final(self, timeline_id: str, **options: Any) -> Any:
        return self._render(options["project"], options["output_path"], options.get("overwrite", False))

    def export_project(self, timeline_id: str, target: str, **options: Any) -> Any:
        return self._render(options["project"], target, options.get("overwrite", False))

    def get_job_status(self, job_id: str) -> Any:
        with Session(engine) as session:
            job = JobRepository(session).get(job_id)
            return job

    def _render(self, project: Project, output_path: str, overwrite: bool) -> ConversionResult:
        output = workspace_path(output_path)
        if output.exists() and not overwrite:
            raise InvalidOperation("El archivo de salida ya existe; confirma overwrite explícitamente.")
        output.parent.mkdir(parents=True, exist_ok=True)
        conversion = FFmpegConverter().convert(project)
        if not conversion.supported or conversion.payload is None:
            raise CapabilityNotAvailable("render_final", plugin_id=self.plugin_id)
        result = run_command("ffmpeg", ["-y" if overwrite else "-n", *conversion.payload["args"], str(output)], timeout=max(settings.command_timeout_seconds, 120), allowed_binaries=_BINARIES, cwd=settings.resolved_workspace_dir)
        if not result.ok:
            raise InvalidOperation(f"ffmpeg falló: {result.error or result.stderr}")
        conversion.payload["log"] = (result.stderr or result.stdout)[-4000:]
        self._mark_verified(["media.cut", "media.concat", "audio.mix", "render.final"])
        return conversion

    def _mark_verified(self, capabilities: list[str]) -> None:
        with Session(engine) as session:
            state = session.get(PluginState, self.plugin_id)
            if state is None:
                return
            config = dict(state.config)
            config["ffmpeg_verified"] = True
            config["ffmpeg_verified_capabilities"] = sorted(set(config.get("ffmpeg_verified_capabilities", [])) | set(capabilities))
            state.config = config
            session.add(state)
            session.commit()
