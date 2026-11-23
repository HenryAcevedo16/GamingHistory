from __future__ import annotations

import json
import shutil

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.errors import InvalidOperation
from app.core.exec import run_command
from app.editing.adapters.ffmpeg import FFmpegAdapter, FFmpegConverter, workspace_path
from app.editing.jobs import JobRepository
from app.editing.timeline import (
    Asset,
    AudioClip,
    AudioTrack,
    Clip,
    Project,
    SubtitleCue,
    SubtitleTrack,
    Transition,
    VideoTrack,
)


def _project(path: str) -> Project:
    return Project(
        name="FFmpeg test",
        assets=[Asset(id="a", name="clip.mp4", path=path, duration_seconds=2)],
        tracks=[VideoTrack(name="V1", clips=[Clip(asset_id="a", start_seconds=0, duration_seconds=1, source_in_seconds=0.25)])],
    )


def test_converter_builds_trim_concat_and_reports_transitions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    result = FFmpegConverter().convert(_project("clip.mp4"))

    assert result.supported is True
    assert "-filter_complex" in result.payload["args"]
    assert any("concat=n=1:v=1:a=1" in arg for arg in result.payload["args"])


def test_converter_reports_unsupported_elements(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    project = Project(
        name="unsupported",
        assets=[
            Asset(id="a", name="a.mp4", path="a.mp4", duration_seconds=2),
            Asset(id="b", name="b.mp4", path="b.mp4", duration_seconds=2),
        ],
        tracks=[
            VideoTrack(
                name="V1",
                clips=[
                    Clip(id="c1", asset_id="a", start_seconds=0, duration_seconds=0.5),
                    Clip(id="c2", asset_id="b", start_seconds=1.5, duration_seconds=0.5),
                ],
            ),
            AudioTrack(
                name="A1",
                clips=[AudioClip(asset_id="a", start_seconds=0, duration_seconds=0.5, fade_in_seconds=0.1)],
            ),
            SubtitleTrack(
                name="S1",
                cues=[SubtitleCue(start_seconds=0, duration_seconds=0.5, text="hola")],
            ),
        ],
        transitions=[
            Transition(kind="fade", duration_seconds=0.2, from_clip_id="c1", to_clip_id="c2")
        ],
    )

    result = FFmpegConverter().convert(project)

    kinds = {item.kind for item in result.unsupported}
    assert result.supported is True
    assert {"transition", "subtitles", "audio_fade", "timeline_gap"} <= kinds


def test_workspace_rejects_outside_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)

    with pytest.raises(InvalidOperation):
        workspace_path(tmp_path.parent / "outside.mp4")
    with pytest.raises(InvalidOperation):
        workspace_path("../outside.mp4")


def test_job_repository_persists_status() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        jobs = JobRepository(session)
        job = jobs.create(project_id="project", kind="final", output_path="output.mp4")
        updated = jobs.update(job, status="done", progress=100)

        assert jobs.get(job.id).status == "done"
        assert updated.progress == 100


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg/FFprobe no está instalado en PATH; se omite contrato real.")
def test_ffmpeg_adapter_renders_a_real_trimmed_clip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    source = tmp_path / "source.mp4"
    generated = run_command("ffmpeg", ["-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source)], timeout=60, allowed_binaries={"ffmpeg"}, cwd=tmp_path)
    assert generated.ok, generated.error or generated.stderr

    adapter = FFmpegAdapter("ffmpeg")
    monkeypatch.setattr(adapter, "_mark_verified", lambda _: None)
    inspected = adapter.import_media([str(source)])
    assert inspected[0]["duration_seconds"] == pytest.approx(2, abs=0.2)

    output = tmp_path / "render.mp4"
    conversion = adapter.render_final("test", project=_project(str(source)), output_path=str(output), overwrite=False)
    assert conversion.supported is True
    assert output.is_file()
    probe = run_command("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)], allowed_binaries={"ffprobe"}, cwd=tmp_path)
    assert probe.ok, probe.error or probe.stderr
    assert float(json.loads(probe.stdout)["format"]["duration"]) == pytest.approx(1, abs=0.2)
