import pytest
from sqlmodel import Session, create_engine

from app.core import db
from app.core.errors import CapabilityNotAvailable, InvalidOperation
from app.editing.adapter import EditorOperation
from app.editing.adapters.resolve import ResolveAdapter, ResolveConverter
from app.editing.adapters.resolve_bridge import ResolveBridgeClient, ResolveBridgeUnavailable
from app.editing.timeline import Asset, Clip, Project, SubtitleCue, SubtitleTrack, VideoTrack
from app.models.plugin import PluginState


class HealthOnlyBridge:
    def __init__(self, root):
        self.root = root

    def health(self):
        return {"connected": True, "edition": "free", "version": "21.0.4.5",
                "policy": {"media_roots": [str(self.root)], "output_roots": [str(self.root)]}}


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
    placement = ResolveConverter.clip_placement(result.payload["tracks"][0], clip,
                                                source_fps=30, timeline_start=1000)
    assert placement == {"start_frame": 15, "end_frame": 45, "record_frame": 1048,
                         "track_index": 1, "media_type": "video"}


@pytest.mark.parametrize(("edition", "version", "available"), [
    ("free", "21.0.4.5", True),
    ("free", "21.1.0", False),
    ("free", "22.0", False),
    ("studio", "21.1.0", True),
], ids=["free-21.0", "free-21.1-blocked", "free-22-blocked", "studio-21.1"])
def test_bridge_compatibility_gate(edition, version, available, tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'resolve.db'}")
    monkeypatch.setattr(db, "engine", engine)
    db.init_db()
    plugin_id = "davinci-resolve"
    with Session(engine) as session:
        session.add(PluginState(plugin_id=plugin_id, connected=True, config={
            "resolve_edition": "free", "resolve_version": "21.0.4.5",
            "resolve_verified": True, "verified_capabilities": ["clip.add"],
        }))
        session.commit()
    bridge = HealthOnlyBridge(tmp_path)
    monkeypatch.setattr(bridge, "health", lambda: {"connected": True, "edition": edition, "version": version})
    adapter = ResolveAdapter(plugin_id, bridge=bridge)
    assert adapter.health_check() is available
    caps = adapter.get_capabilities()
    assert f"Versión: {version}." in caps.notes
    assert f"Edición detectada: {edition.title()}." in caps.notes
    assert (EditorOperation.CREATE_PROJECT in caps.operations) is available
    if not available:
        assert not caps.capability_ids and not caps.verified
        with pytest.raises(ResolveBridgeUnavailable, match="requiere Studio"):
            adapter.create_project("Must not reach bridge write")
        with Session(engine) as session:
            state = session.get(PluginState, plugin_id)
            assert not state.connected
            assert "verified_capabilities" not in state.config
