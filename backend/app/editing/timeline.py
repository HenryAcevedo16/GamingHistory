"""Unified, editor-neutral timeline model.

This is the project's source of truth. It keeps scene/asset IDs, positions,
durations, tracks, transitions, audio, subtitles, effects and metadata. Every
adapter conversion goes FROM this model; nothing is inferred back from an
external editor.

Validation is strict on purpose: an invalid timeline must fail before any
editor receives it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.editing.notes import NoteText, sanitize_note

_EPSILON = 1e-6


def new_id() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Asset(StrictModel):
    """A media resource referenced by the timeline. IDs are preserved."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    path: str | None = None
    kind: Literal["video", "audio", "image", "subtitle", "other"] = "video"
    duration_seconds: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    note: NoteText | None = Field(default=None, repr=False)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return (sanitize_note(value) or None) if value is not None else None


class Scene(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    order: int = Field(default=0, ge=0)
    asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Effect(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    name: str = Field(min_length=1)
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Clip(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    asset_id: str = Field(min_length=1)
    name: str | None = None
    start_seconds: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(gt=0.0)
    source_in_seconds: float = Field(default=0.0, ge=0.0)
    effects: list[Effect] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioClip(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    asset_id: str = Field(min_length=1)
    name: str | None = None
    start_seconds: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(gt=0.0)
    source_in_seconds: float = Field(default=0.0, ge=0.0)
    gain_db: float = 0.0
    fade_in_seconds: float = Field(default=0.0, ge=0.0)
    fade_out_seconds: float = Field(default=0.0, ge=0.0)
    effects: list[Effect] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fades_fit(self) -> "AudioClip":
        if self.fade_in_seconds + self.fade_out_seconds > self.duration_seconds + _EPSILON:
            raise ValueError("Los fundidos de audio no pueden superar la duración del clip.")
        return self


class SubtitleCue(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    start_seconds: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(gt=0.0)
    text: str = Field(min_length=1)
    language: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Transition(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    kind: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0.0)
    from_clip_id: str = Field(min_length=1)
    to_clip_id: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _distinct_clips(self) -> "Transition":
        if self.from_clip_id == self.to_clip_id:
            raise ValueError("Una transición necesita dos clips distintos.")
        return self


class TrackBase(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    name: str = Field(min_length=1)
    enabled: bool = True
    locked: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def _assert_no_overlap(items: list[Any], label: str) -> None:
    ordered = sorted(items, key=lambda item: item.start_seconds)
    for previous, current in zip(ordered, ordered[1:]):
        previous_end = previous.start_seconds + previous.duration_seconds
        if current.start_seconds < previous_end - _EPSILON:
            raise ValueError(
                f"{label}: '{current.id}' empieza en {current.start_seconds:g}s, "
                f"antes de que termine '{previous.id}' ({previous_end:g}s)."
            )


class VideoTrack(TrackBase):
    kind: Literal["video"] = "video"
    clips: list[Clip] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> "VideoTrack":
        _assert_no_overlap(self.clips, "Solapamiento en pista de vídeo")
        return self


class AudioTrack(TrackBase):
    kind: Literal["audio"] = "audio"
    clips: list[AudioClip] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> "AudioTrack":
        _assert_no_overlap(self.clips, "Solapamiento en pista de audio")
        return self


class SubtitleTrack(TrackBase):
    kind: Literal["subtitle"] = "subtitle"
    cues: list[SubtitleCue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> "SubtitleTrack":
        _assert_no_overlap(self.cues, "Solapamiento en pista de subtítulos")
        return self


Track = Annotated[
    VideoTrack | AudioTrack | SubtitleTrack,
    Field(discriminator="kind"),
]


class TimelinePayload(StrictModel):
    """The mutable part of a project: tracks and transitions."""

    tracks: list[Track] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class Project(StrictModel):
    id: str = Field(default_factory=new_id, min_length=1)
    name: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    assets: list[Asset] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)

    def _track_items(self) -> list[Clip | AudioClip | SubtitleCue]:
        items: list[Clip | AudioClip | SubtitleCue] = []
        for track in self.tracks:
            if isinstance(track, VideoTrack):
                items.extend(track.clips)
            elif isinstance(track, AudioTrack):
                items.extend(track.clips)
            else:
                items.extend(track.cues)
        return items

    @model_validator(mode="after")
    def _validate_references(self) -> "Project":
        if not self.name.strip():
            raise ValueError("El proyecto necesita un nombre.")

        asset_ids = [asset.id for asset in self.assets]
        scene_ids = [scene.id for scene in self.scenes]
        track_ids = [track.id for track in self.tracks]
        items = self._track_items()
        item_ids = [item.id for item in items]
        effect_ids = [
            effect.id
            for item in items
            for effect in getattr(item, "effects", [])
        ]

        for values, label in (
            (asset_ids, "recursos"),
            (scene_ids, "escenas"),
            (track_ids, "pistas"),
            (item_ids, "clips/subtítulos"),
            (effect_ids, "efectos"),
            ([transition.id for transition in self.transitions], "transiciones"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Hay IDs duplicados en {label}.")

        asset_set = set(asset_ids)
        durations = {asset.id: asset.duration_seconds for asset in self.assets}

        for scene in self.scenes:
            missing = [asset_id for asset_id in scene.asset_ids if asset_id not in asset_set]
            if missing:
                raise ValueError(
                    f"La escena '{scene.id}' referencia recursos inexistentes: {missing}."
                )

        for item in items:
            asset_id = getattr(item, "asset_id", None)
            if asset_id is not None and asset_id not in asset_set:
                raise ValueError(f"'{item.id}' referencia un recurso inexistente: '{asset_id}'.")
            if asset_id is not None:
                duration = durations.get(asset_id, 0.0)
                source_in = getattr(item, "source_in_seconds", 0.0)
                item_duration = getattr(item, "duration_seconds", 0.0)
                if duration > 0 and source_in + item_duration > duration + _EPSILON:
                    raise ValueError(
                        f"'{item.id}' lee {source_in + item_duration:g}s de '{asset_id}', "
                        f"que dura {duration:g}s."
                    )

        item_set = set(item_ids)
        for transition in self.transitions:
            for clip_id in (transition.from_clip_id, transition.to_clip_id):
                if clip_id not in item_set:
                    raise ValueError(
                        f"La transición '{transition.id}' referencia un clip inexistente: '{clip_id}'."
                    )
        return self

    def with_timeline(self, payload: TimelinePayload) -> "Project":
        """Return a re-validated copy with new tracks/transitions."""
        data = self.model_dump()
        data["tracks"] = [track.model_dump() for track in payload.tracks]
        data["transitions"] = [transition.model_dump() for transition in payload.transitions]
        return Project.model_validate(data)

    def timeline(self) -> TimelinePayload:
        return TimelinePayload(tracks=self.tracks, transitions=self.transitions)
