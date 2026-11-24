from __future__ import annotations

import pytest

from app.core.errors import InvalidOperation
from app.editing.adapter import EditorOperation
from app.editing.registry import AdapterRegistry
from app.editing.router import EditingRouter, INTENT_SPECS
from app.plugins.manifest import KnownCosts, PluginCapability
from app.plugins.schemas import PluginView
from tests.dummy_adapter import DummyAdapter


def make_view(
    plugin_id: str,
    *,
    name: str | None = None,
    install_status: str = "installed",
    enabled: bool = True,
    connected: bool = True,
    connection_type: str = "local-binary",
    capabilities: tuple[str, ...] = (),
    pricing: str = "free",
) -> PluginView:
    return PluginView(
        id=plugin_id,
        name=name or plugin_id,
        version="0.1.0",
        description="",
        category="test",
        connection_type=connection_type,
        install_status=install_status,
        enabled=enabled,
        connected=connected,
        display_status="connected" if connected else (
            "disabled" if not enabled else "installed"
        ),
        known_costs=KnownCosts(pricing=pricing),
        capabilities=[
            PluginCapability(id=capability, label=capability) for capability in capabilities
        ],
    )


def real_world_views() -> list[PluginView]:
    return [
        make_view(
            "ffmpeg",
            name="FFmpeg",
            capabilities=("media.cut", "media.concat", "render.final"),
        ),
        make_view(
            "vectcut-capcut",
            name="CapCut / VectCutAPI",
            install_status="not_installed",
            connected=False,
            connection_type="mcp-http",
            capabilities=("draft.create", "track.add"),
        ),
        make_view(
            "davinci-resolve",
            name="DaVinci Resolve",
            connected=False,
            capabilities=("timeline.create", "clip.add"),
        ),
        make_view(
            "descript",
            name="Descript",
            install_status="not_installed",
            connected=False,
            connection_type="cloud-api",
            pricing="paid",
            capabilities=("edit.by_instruction",),
        ),
    ]


def decisions_by_operation(router: EditingRouter, **kwargs):
    return {decision.operation: decision for decision in router.decide_all(**kwargs)}


def test_default_rules_select_only_connected_capable_plugins() -> None:
    decisions = decisions_by_operation(EditingRouter(real_world_views()))

    assert decisions["auto_assembly"].selected is not None
    assert decisions["auto_assembly"].selected.plugin_id == "ffmpeg"
    assert decisions["auto_assembly"].selected.executable is True
    assert decisions["auto_assembly"].selected.adapter_registered is True
    assert decisions["auto_assembly"].capability_source == "adapter"

    for operation in ("editable_draft", "professional_edit", "transcript_edit"):
        assert decisions[operation].selected is None

    reasons = {
        candidate.plugin_id: candidate.reason
        for candidate in decisions["editable_draft"].candidates
    }
    assert "Dependencias ausentes" in reasons["vectcut-capcut"]
    assert "Sin conexión verificada" in reasons["davinci-resolve"]
    assert "Dependencias ausentes" in reasons["descript"]


def test_disabled_plugin_is_never_selected() -> None:
    views = [
        make_view(
            "ffmpeg",
            enabled=False,
            capabilities=("media.cut", "media.concat"),
        )
    ]
    decision = EditingRouter(views).decide("auto_assembly")

    assert decision.selected is None
    assert decision.candidates[0].eligible is False
    assert "deshabilitado" in decision.candidates[0].reason.lower()


def test_connected_plugin_can_win_for_its_intent() -> None:
    views = [
        make_view(
            "davinci-resolve",
            connected=True,
            capabilities=("timeline.create", "clip.add"),
        )
    ]
    registry = AdapterRegistry()
    registry.register("davinci-resolve", lambda plugin_id: DummyAdapter(
        plugin_id, {EditorOperation.CREATE_TIMELINE, EditorOperation.ADD_CLIP}
    ))
    router = EditingRouter(views, adapters=registry)
    assert router.decide("professional_edit").selected is None
    views[0].verified_capabilities = ["timeline.create", "clip.add"]
    decision = router.decide("professional_edit")

    assert decision.selected is not None
    assert decision.selected.plugin_id == "davinci-resolve"


def test_cloud_plugin_requires_explicit_authorization() -> None:
    views = [
        make_view(
            "descript",
            connection_type="cloud-api",
            pricing="paid",
            capabilities=("edit.by_instruction",),
        )
    ]

    blocked = EditingRouter(views).decide("transcript_edit")
    assert blocked.selected is None
    assert "autorización explícita" in blocked.candidates[0].reason

    allowed = EditingRouter(views).decide("transcript_edit", cloud_authorized=True)
    assert allowed.selected is not None
    assert allowed.selected.plugin_id == "descript"


def test_ffmpeg_adapter_capabilities_override_manifest_declarations() -> None:
    views = [make_view("ffmpeg", capabilities=("render.final",))]

    decision = EditingRouter(views).decide("auto_assembly")

    assert decision.selected is not None
    assert decision.selected.plugin_id == "ffmpeg"
    assert decision.capability_source == "adapter"


def test_manual_selection_overrides_default_preference() -> None:
    views = [
        make_view("ffmpeg", capabilities=("media.cut", "media.concat")),
        make_view(
            "other-editor",
            capabilities=("media.cut", "media.concat"),
        ),
    ]

    decision = EditingRouter(views).decide(
        "auto_assembly", manual_plugin_id="other-editor"
    )

    assert decision.selected is not None
    assert decision.selected.plugin_id == "other-editor"
    ffmpeg = next(
        candidate for candidate in decision.candidates if candidate.plugin_id == "ffmpeg"
    )
    assert "selección manual" in ffmpeg.reason


def test_invalid_manual_selection_explains_why() -> None:
    views = [
        make_view("ffmpeg", capabilities=("media.cut", "media.concat")),
        make_view(
            "descript",
            install_status="not_installed",
            connected=False,
            connection_type="cloud-api",
            capabilities=("edit.by_instruction",),
        ),
    ]

    decision = EditingRouter(views).decide(
        "auto_assembly", manual_plugin_id="descript", cloud_authorized=True
    )

    assert decision.selected is None
    assert "no es válida" in decision.explanation
    assert "Dependencias ausentes" in decision.explanation


def test_registered_adapter_marks_decision_executable() -> None:
    registry = AdapterRegistry()
    registry.register(
        "ffmpeg",
        lambda plugin_id: DummyAdapter(plugin_id, {EditorOperation.CREATE_TIMELINE}),
    )
    views = [make_view("ffmpeg", capabilities=("media.cut", "media.concat"))]

    decision = EditingRouter(views, adapters=registry).decide("auto_assembly")

    assert decision.selected is not None
    assert decision.selected.adapter_registered is True
    assert decision.selected.executable is True
    assert "Fase 3" not in decision.explanation


def test_unknown_operation_raises_invalid_operation() -> None:
    with pytest.raises(InvalidOperation):
        EditingRouter(real_world_views()).decide("make_coffee")


def test_all_spec_defaults_are_declared() -> None:
    preferred = {spec.id: spec.preferred_plugin_id for spec in INTENT_SPECS}

    assert preferred == {
        "auto_assembly": "ffmpeg",
        "editable_draft": "vectcut-capcut",
        "professional_edit": "davinci-resolve",
        "transcript_edit": "descript",
    }
