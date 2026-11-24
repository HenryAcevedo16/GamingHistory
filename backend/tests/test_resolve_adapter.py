import pytest

from app.core.errors import CapabilityNotAvailable, InvalidOperation
from app.editing.adapters.resolve import ResolveAdapter, ResolveConverter
from app.editing.adapters.resolve_bridge import ResolveBridgeClient, ResolveBridgeUnavailable
from app.editing.timeline import Asset, Clip, Project, SubtitleCue, SubtitleTrack, VideoTrack


class HealthOnlyBridge:
    def __init__(self, root):
        self.root = root

    def health(self):
        return {"connected": True, "policy": {"media_roots": [str(self.root)], "output_roots": [str(self.root)]}}


def test_paths_outside_resolve_policy_never_reach_bridge_write(tmp_path, monkeypatch):
    media = tmp_path / "outside.mov"
    media.touch()
    root = tmp_path / "allowed"
    root.mkdir()
    adapter = ResolveAdapter("davinci-resolve", bridge=HealthOnlyBridge(root))
    monkeypatch.setattr(adapter, "_remember_health", lambda _: None)
    with pytest.raises(InvalidOperation, match="fuera de las raíces"):
        adapter.import_media([str(media)])
    with pytest.raises(InvalidOperation, match="CustomName"):
        adapter.render_final("current", settings={"TargetDir": str(root), "CustomName": "../outside"})
    with pytest.raises(CapabilityNotAvailable):
        adapter.add_subtitles("current", [])


def test_bridge_rejects_non_loopback():
    client = ResolveBridgeClient({"host": "192.0.2.1", "port": 49632, "token": "test-only"})
    with pytest.raises(ResolveBridgeUnavailable, match="127.0.0.1"):
        client.health()


def test_resolve_plan_keeps_source_time_and_reports_unexported_subtitles():
    project = Project(
        name="Resolve plan", metadata={"fps": 24}, assets=[Asset(id="a", name="Source", path="source.mov")],
        tracks=[VideoTrack(name="V1", clips=[Clip(asset_id="a", start_seconds=2, duration_seconds=1, source_in_seconds=0.5)]),
                SubtitleTrack(name="Sub", cues=[SubtitleCue(text="Hello", duration_seconds=1)])],
    )
    result = ResolveConverter().convert(project)
    assert result.supported and not result.complete
    assert [item.kind for item in result.unsupported] == ["subtitles"]
    clip = result.payload["tracks"][0]["clips"][0]
    assert clip["record_offset_frames"] == 48 and clip["source_in_seconds"] == 0.5
