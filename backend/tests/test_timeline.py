from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from app.core.errors import ProjectNotFound
from app.editing.persistence import ProjectRepository
from app.editing.timeline import (
    Asset,
    AudioClip,
    AudioTrack,
    Clip,
    Project,
    Scene,
    SubtitleCue,
    SubtitleTrack,
    TimelinePayload,
    Transition,
    VideoTrack,
)


def make_project() -> Project:
    return Project(
        id="project-1",
        name="Documental de prueba",
        metadata={"fps": 30},
        assets=[
            Asset(id="video-1", name="Intro", kind="video", duration_seconds=10.0),
            Asset(id="audio-1", name="Música", kind="audio", duration_seconds=30.0),
        ],
        scenes=[
            Scene(id="scene-1", name="Intro", order=0, asset_ids=["video-1"]),
        ],
        tracks=[
            VideoTrack(
                id="track-v1",
                name="Vídeo 1",
                clips=[
                    Clip(
                        id="clip-1",
                        asset_id="video-1",
                        start_seconds=0.0,
                        duration_seconds=4.0,
                        source_in_seconds=1.0,
                    )
                ],
            ),
            AudioTrack(
                id="track-a1",
                name="Música",
                clips=[
                    AudioClip(
                        id="audio-clip-1",
                        asset_id="audio-1",
                        start_seconds=0.0,
                        duration_seconds=4.0,
                    )
                ],
            ),
            SubtitleTrack(
                id="track-s1",
                name="Subtítulos",
                cues=[
                    SubtitleCue(
                        id="cue-1",
                        start_seconds=0.5,
                        duration_seconds=1.5,
                        text="Hola",
                    )
                ],
            ),
        ],
    )


def test_valid_project_serializes_and_roundtrips() -> None:
    project = make_project()

    restored = Project.model_validate_json(project.model_dump_json())

    assert restored == project
    assert restored.assets[0].id == "video-1"
    assert restored.tracks[0].kind == "video"
    assert restored.timeline().tracks[0].id == "track-v1"


def test_video_track_rejects_overlap() -> None:
    with pytest.raises(ValidationError, match="Solapamiento"):
        VideoTrack(
            id="track",
            name="V1",
            clips=[
                Clip(id="a", asset_id="x", start_seconds=0.0, duration_seconds=5.0),
                Clip(id="b", asset_id="x", start_seconds=4.0, duration_seconds=2.0),
            ],
        )


def test_audio_track_rejects_overlap() -> None:
    with pytest.raises(ValidationError, match="Solapamiento"):
        AudioTrack(
            id="track",
            name="A1",
            clips=[
                AudioClip(id="a", asset_id="x", start_seconds=0.0, duration_seconds=5.0),
                AudioClip(id="b", asset_id="x", start_seconds=4.999, duration_seconds=1.0),
            ],
        )


def test_subtitle_track_rejects_overlap() -> None:
    with pytest.raises(ValidationError, match="Solapamiento"):
        SubtitleTrack(
            id="track",
            name="S1",
            cues=[
                SubtitleCue(id="a", start_seconds=0.0, duration_seconds=2.0, text="A"),
                SubtitleCue(id="b", start_seconds=1.0, duration_seconds=2.0, text="B"),
            ],
        )


def test_adjacent_clips_are_allowed() -> None:
    track = VideoTrack(
        id="track",
        name="V1",
        clips=[
            Clip(id="a", asset_id="x", start_seconds=0.0, duration_seconds=5.0),
            Clip(id="b", asset_id="x", start_seconds=5.0, duration_seconds=2.0),
        ],
    )
    assert len(track.clips) == 2


def test_clip_duration_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Clip(id="a", asset_id="x", start_seconds=0.0, duration_seconds=0.0)


def test_missing_asset_reference_is_rejected() -> None:
    with pytest.raises(ValidationError, match="recurso inexistente"):
        Project(
            name="Doc",
            assets=[Asset(id="a1", name="A")],
            tracks=[
                VideoTrack(
                    id="v1",
                    name="V1",
                    clips=[Clip(id="c1", asset_id="missing", duration_seconds=1.0)],
                )
            ],
        )


def test_scene_reference_must_exist() -> None:
    with pytest.raises(ValidationError, match="recursos inexistentes"):
        Project(
            name="Doc",
            scenes=[Scene(id="s1", name="Intro", asset_ids=["missing"])],
        )


def test_transition_must_reference_existing_clips() -> None:
    project_data = make_project().model_dump()
    project_data["transitions"] = [
        {
            "id": "tr-1",
            "kind": "crossfade",
            "duration_seconds": 0.5,
            "from_clip_id": "clip-1",
            "to_clip_id": "missing",
        }
    ]

    with pytest.raises(ValidationError, match="clip inexistente"):
        Project.model_validate(project_data)


def test_transition_requires_distinct_clips() -> None:
    with pytest.raises(ValidationError, match="dos clips distintos"):
        Transition(
            kind="crossfade",
            duration_seconds=0.5,
            from_clip_id="clip-1",
            to_clip_id="clip-1",
        )


def test_source_range_cannot_exceed_asset_duration() -> None:
    with pytest.raises(ValidationError, match="que dura"):
        Project(
            name="Doc",
            assets=[Asset(id="a1", name="A", duration_seconds=5.0)],
            tracks=[
                VideoTrack(
                    id="v1",
                    name="V1",
                    clips=[
                        Clip(
                            id="c1",
                            asset_id="a1",
                            source_in_seconds=4.0,
                            duration_seconds=3.0,
                        )
                    ],
                )
            ],
        )


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="IDs duplicados"):
        Project(
            name="Doc",
            assets=[
                Asset(id="a1", name="A", duration_seconds=10.0),
                Asset(id="a1", name="B", duration_seconds=10.0),
            ],
        )


def test_audio_fades_cannot_exceed_duration() -> None:
    with pytest.raises(ValidationError, match="fundidos"):
        AudioClip(
            asset_id="a1",
            duration_seconds=2.0,
            fade_in_seconds=1.5,
            fade_out_seconds=1.0,
        )


def test_with_timeline_revalidates_references() -> None:
    project = make_project()
    payload = TimelinePayload(
        tracks=[
            VideoTrack(
                id="track-v2",
                name="V2",
                clips=[
                    Clip(
                        id="clip-2",
                        asset_id="missing",
                        duration_seconds=1.0,
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValidationError, match="recurso inexistente"):
        project.with_timeline(payload)


def test_persistence_saves_and_reads(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'timeline.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    project = make_project()
    with Session(engine) as session:
        repository = ProjectRepository(session)
        saved = repository.save(project)
        assert saved.id == project.id

        loaded = repository.get(project.id)
        assert loaded.name == project.name
        assert loaded.tracks[1].kind == "audio"

        updated = Project.model_validate({**loaded.model_dump(), "name": "Renombrado"})
        repository.save(updated)
        assert repository.get(project.id).name == "Renombrado"
        assert [item.id for item in repository.list()] == [project.id]

        with pytest.raises(ProjectNotFound):
            repository.get("missing")
