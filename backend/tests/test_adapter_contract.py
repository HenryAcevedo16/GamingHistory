from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from app.core.errors import (
    AdapterNotRegistered,
    CapabilityNotAvailable,
    InvalidOperation,
    PluginNotConnected,
)
from app.editing.adapter import EditorOperation, execute_operation
from app.editing.registry import AdapterRegistry
from app.models.plugin import PluginState
from tests.dummy_adapter import DummyAdapter


def _state_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.core import db

    engine = create_engine(
        f"sqlite:///{tmp_path / 'state.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db, "engine", engine)
    db.init_db()
    return engine


def _save_state(engine, *, enabled: bool, connected: bool) -> None:
    with Session(engine) as session:
        session.add(PluginState(plugin_id="dummy", enabled=enabled, connected=connected))
        session.commit()


def test_unsupported_method_raises_capability_not_available() -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})

    with pytest.raises(CapabilityNotAvailable) as excinfo:
        adapter.remove_clip("timeline-1", "clip-1")

    assert excinfo.value.details == {
        "capability": "remove_clip",
        "plugin_id": "dummy",
    }
    assert adapter.calls == []


def test_wrapper_queries_capabilities_before_executing(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})
    monkeypatch.setattr("app.editing.adapter._plugin_is_connected", lambda _: True)

    result = execute_operation(
        adapter,
        EditorOperation.CREATE_TIMELINE,
        {"project_id": "p1", "name": "Doc"},
    )

    assert result["id"] == "timeline-1"
    assert adapter.capability_calls == 1
    assert adapter.calls[0][0] == "create_timeline"


def test_wrapper_rejects_unsupported_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})
    monkeypatch.setattr("app.editing.adapter._plugin_is_connected", lambda _: True)

    with pytest.raises(CapabilityNotAvailable) as excinfo:
        execute_operation(adapter, EditorOperation.RENDER_FINAL, {"timeline_id": "t1"})

    assert excinfo.value.capability == "render_final"
    assert adapter.capability_calls == 1
    assert adapter.calls == []


def test_wrapper_rejects_unknown_operation_name() -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})

    with pytest.raises(InvalidOperation) as excinfo:
        execute_operation(adapter, "make_magic")

    assert "make_magic" in excinfo.value.message
    assert adapter.calls == []


def test_wrapper_rejects_disconnected_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})
    monkeypatch.setattr("app.editing.adapter._plugin_is_connected", lambda _: False)

    with pytest.raises(PluginNotConnected):
        execute_operation(
            adapter,
            EditorOperation.CREATE_TIMELINE,
            {"project_id": "p1", "name": "Doc"},
        )

    assert adapter.calls == []


def test_wrapper_rejects_invalid_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})
    monkeypatch.setattr("app.editing.adapter._plugin_is_connected", lambda _: True)

    with pytest.raises(InvalidOperation):
        execute_operation(adapter, EditorOperation.CREATE_TIMELINE, {"wrong": 1})

    assert adapter.capability_calls == 1
    assert adapter.calls == []


def test_wrapper_rejects_disconnected_plugin_from_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _state_engine(tmp_path, monkeypatch)
    _save_state(engine, enabled=True, connected=False)
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})

    with pytest.raises(PluginNotConnected) as excinfo:
        execute_operation(
            adapter,
            EditorOperation.CREATE_TIMELINE,
            {"project_id": "p1", "name": "Doc"},
        )

    assert excinfo.value.details["plugin_id"] == "dummy"
    assert adapter.capability_calls == 0
    assert adapter.calls == []


def test_wrapper_rejects_disabled_plugin_from_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _state_engine(tmp_path, monkeypatch)
    _save_state(engine, enabled=False, connected=True)
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})

    with pytest.raises(PluginNotConnected):
        execute_operation(
            adapter,
            EditorOperation.CREATE_TIMELINE,
            {"project_id": "p1", "name": "Doc"},
        )

    assert adapter.capability_calls == 0
    assert adapter.calls == []


def test_wrapper_rejects_plugin_without_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_engine(tmp_path, monkeypatch)
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})

    with pytest.raises(PluginNotConnected):
        execute_operation(
            adapter,
            EditorOperation.CREATE_TIMELINE,
            {"project_id": "p1", "name": "Doc"},
        )

    assert adapter.calls == []


def test_execute_operation_does_not_accept_connected_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DummyAdapter(operations={EditorOperation.CREATE_TIMELINE})
    monkeypatch.setattr("app.editing.adapter._plugin_is_connected", lambda _: True)

    with pytest.raises(TypeError):
        execute_operation(
            adapter,
            EditorOperation.CREATE_TIMELINE,
            {"project_id": "p1", "name": "Doc"},
            connected=True,
        )

    assert adapter.calls == []


def test_registry_creates_registered_adapter() -> None:
    registry = AdapterRegistry()
    registry.register(
        "dummy",
        lambda plugin_id: DummyAdapter(plugin_id, {EditorOperation.RENDER_PREVIEW}),
    )

    assert registry.has("dummy")
    adapter = registry.create("dummy")
    assert isinstance(adapter, DummyAdapter)
    assert adapter.plugin_id == "dummy"


def test_registry_unknown_plugin_raises() -> None:
    registry = AdapterRegistry()

    with pytest.raises(AdapterNotRegistered):
        registry.create("nope")


def test_registry_rejects_duplicates_and_supports_replace() -> None:
    registry = AdapterRegistry()
    registry.register("dummy", DummyAdapter)

    with pytest.raises(ValueError):
        registry.register("dummy", DummyAdapter)

    registry.register("dummy", DummyAdapter, replace=True)
    assert registry.plugin_ids() == ["dummy"]
