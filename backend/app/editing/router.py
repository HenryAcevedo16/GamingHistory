"""EditingRouter: picks an editor for an intent using real plugin state.

Rules from SPEC.md:
- montaje automático -> FFmpeg
- borrador editable -> VectCutAPI/CapCut
- edición profesional -> DaVinci Resolve
- edición por transcripción -> Descript

Hard rejections come before scoring: disabled, not installed, not connected,
missing declared capabilities, and cloud uploads without explicit permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.errors import InvalidOperation
from app.editing.adapter import EditorOperation
from app.editing.registry import AdapterRegistry, default_registry
from app.editing.schemas import (
    RouterCandidate,
    RouterDecision,
    RouterOperation,
    RouterSelection,
)
from app.plugins.schemas import PluginView

INSTALLED_STATUSES = {"installed", "connected"}
CLOUD_CONNECTION_TYPES = {"cloud-api"}
COST_RANK = {"free": 30, "freemium": 20, "paid": 10, "unknown": 0}
PREFERENCE_WEIGHT = 1000
CAPABILITY_WEIGHT = 5


@dataclass(frozen=True)
class IntentSpec:
    id: RouterOperation
    label: str
    description: str
    preferred_plugin_id: str
    required_capabilities: tuple[str, ...]
    adapter_operation: EditorOperation


INTENT_SPECS: tuple[IntentSpec, ...] = (
    IntentSpec(
        id="auto_assembly",
        label="Montaje automático",
        description="Corta, une y renderiza sin abrir un editor.",
        preferred_plugin_id="ffmpeg",
        required_capabilities=("media.cut", "media.concat"),
        adapter_operation=EditorOperation.CREATE_TIMELINE,
    ),
    IntentSpec(
        id="editable_draft",
        label="Borrador editable",
        description="Genera un borrador para revisar en CapCut.",
        preferred_plugin_id="vectcut-capcut",
        required_capabilities=("draft.create", "track.add"),
        adapter_operation=EditorOperation.CREATE_PROJECT,
    ),
    IntentSpec(
        id="professional_edit",
        label="Edición profesional",
        description="Timelines y clips dentro de DaVinci Resolve.",
        preferred_plugin_id="davinci-resolve",
        required_capabilities=("timeline.create", "clip.add"),
        adapter_operation=EditorOperation.CREATE_TIMELINE,
    ),
    IntentSpec(
        id="transcript_edit",
        label="Edición por transcripción",
        description="Edición guiada por texto en Descript (envía material a la nube).",
        preferred_plugin_id="descript",
        required_capabilities=("edit.by_instruction",),
        adapter_operation=EditorOperation.IMPORT_MEDIA,
    ),
)

_SPECS_BY_ID = {spec.id: spec for spec in INTENT_SPECS}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EditingRouter:
    def __init__(
        self,
        views: list[PluginView],
        *,
        adapters: AdapterRegistry | None = None,
    ) -> None:
        self.views = views
        self.adapters = adapters or default_registry

    def decide(
        self,
        operation: RouterOperation | str,
        *,
        manual_plugin_id: str | None = None,
        cloud_authorized: bool = False,
        required_capabilities: list[str] | None = None,
        preferred_plugin_id: str | None = None,
    ) -> RouterDecision:
        spec = _SPECS_BY_ID.get(operation)  # type: ignore[arg-type]
        if spec is None:
            raise InvalidOperation(
                f"Tipo de operación desconocido: '{operation}'.",
                details={"available_operations": sorted(_SPECS_BY_ID)},
            )

        required = tuple(required_capabilities or spec.required_capabilities)
        preferred = preferred_plugin_id or spec.preferred_plugin_id

        if not self.views:
            return RouterDecision(
                operation=spec.id,
                label=spec.label,
                description=spec.description,
                required_capabilities=list(required),
                adapter_operation=spec.adapter_operation.value,
                capability_source="manifest",
                selected=None,
                candidates=[],
                discarded=[],
                explanation="No hay plugins en el catálogo: nada puede editar.",
                generated_at=_utcnow(),
            )

        candidates: list[RouterCandidate] = []
        scores: dict[str, int] = {}

        for view in self.views:
            candidate, score = self._evaluate(
                view,
                required=required,
                preferred=preferred,
                manual_plugin_id=manual_plugin_id,
                cloud_authorized=cloud_authorized,
            )
            candidates.append(candidate)
            if candidate.eligible:
                scores[view.id] = score

        eligible = [candidate for candidate in candidates if candidate.eligible]
        selected: RouterCandidate | None = None
        if eligible:
            selected = max(
                eligible,
                key=lambda candidate: (
                    scores.get(candidate.plugin_id, 0),
                    candidate.connected,
                    candidate.plugin_id,
                ),
            )

        if selected is not None:
            adapter_registered = self.adapters.has(selected.plugin_id)
            selected.selected = True
            selected.reason = self._selection_reason(selected, spec, preferred)
            discarded = [item for item in candidates if not item.selected]
            explanation = (
                f"Se elige {selected.name} para {spec.label.lower()} porque "
                f"{selected.reason.lower()} "
                f"{len(discarded)} plugin(s) descartados."
            )
            if not adapter_registered:
                explanation += (
                    " Aviso: todavía no hay adaptador registrado para este plugin, "
                    "así que esta decisión no ejecuta nada (Fase 3)."
                )
            selection = RouterSelection(
                plugin_id=selected.plugin_id,
                name=selected.name,
                reason=selected.reason,
                score=scores.get(selected.plugin_id, 0),
                adapter_registered=adapter_registered,
                executable=adapter_registered,
            )
        else:
            discarded = candidates
            details = "; ".join(
                f"{candidate.plugin_id}: {candidate.reason}" for candidate in candidates
            )
            explanation = f"Ningún plugin puede ejecutar {spec.label.lower()}. {details}"
            if manual_plugin_id:
                manual = next(
                    (item for item in candidates if item.plugin_id == manual_plugin_id),
                    None,
                )
                if manual is not None and not manual.eligible:
                    explanation = (
                        f"La selección manual '{manual_plugin_id}' no es válida: "
                        f"{manual.reason} {details}"
                    )
            selection = None

        return RouterDecision(
            operation=spec.id,
            label=spec.label,
            description=spec.description,
            required_capabilities=list(required),
            adapter_operation=spec.adapter_operation.value,
            capability_source="manifest",
            selected=selection,
            candidates=candidates,
            discarded=discarded,
            explanation=explanation,
            generated_at=_utcnow(),
        )

    def decide_all(
        self,
        *,
        cloud_authorized: bool = False,
        manual_plugin_id: str | None = None,
    ) -> list[RouterDecision]:
        return [
            self.decide(
                spec.id,
                cloud_authorized=cloud_authorized,
                manual_plugin_id=manual_plugin_id,
            )
            for spec in INTENT_SPECS
        ]

    # -- internals ---------------------------------------------------------

    def _evaluate(
        self,
        view: PluginView,
        *,
        required: tuple[str, ...],
        preferred: str,
        manual_plugin_id: str | None,
        cloud_authorized: bool,
    ) -> tuple[RouterCandidate, int]:
        installed = view.install_status in INSTALLED_STATUSES
        adapter_registered = self.adapters.has(view.id)
        available_capabilities = {
            capability.id
            for capability in view.capabilities
            if capability.status != "unsupported"
        }
        missing = [capability for capability in required if capability not in available_capabilities]

        def candidate(reason: str, *, eligible: bool) -> RouterCandidate:
            return RouterCandidate(
                plugin_id=view.id,
                name=view.name,
                eligible=eligible,
                reason=reason,
                enabled=view.enabled,
                installed=installed,
                connected=view.connected,
                adapter_registered=adapter_registered,
                pricing=view.known_costs.pricing,
                missing_capabilities=missing,
            )

        if manual_plugin_id and view.id != manual_plugin_id:
            return candidate(f"Descartado por selección manual de '{manual_plugin_id}'.", eligible=False), 0
        if not view.enabled:
            return candidate("Plugin deshabilitado.", eligible=False), 0
        if not installed:
            return (
                candidate(
                    f"Dependencias ausentes: no está instalado (estado '{view.install_status}').",
                    eligible=False,
                ),
                0,
            )
        if not view.connected:
            return candidate("Sin conexión verificada.", eligible=False), 0
        if view.connection_type in CLOUD_CONNECTION_TYPES and not cloud_authorized:
            return (
                candidate(
                    "Enviaría material a la nube y falta autorización explícita.",
                    eligible=False,
                ),
                0,
            )
        if missing:
            return (
                candidate(
                    "No declara las capacidades requeridas: " + ", ".join(missing) + ".",
                    eligible=False,
                ),
                0,
            )

        score = (
            (PREFERENCE_WEIGHT if view.id == preferred else 0)
            + CAPABILITY_WEIGHT * len(required)
            + COST_RANK.get(view.known_costs.pricing, 0)
        )
        return (
            candidate(
                "Cumple capacidades, instalación y conexión; "
                f"coste '{view.known_costs.pricing}'.",
                eligible=True,
            ),
            score,
        )

    @staticmethod
    def _selection_reason(
        candidate: RouterCandidate, spec: IntentSpec, preferred: str
    ) -> str:
        reasons: list[str] = []
        if candidate.plugin_id == preferred:
            reasons.append("es el editor por defecto para esta operación")
        reasons.append("está conectado y declara las capacidades necesarias")
        reasons.append(f"coste '{candidate.pricing}'")
        return "; ".join(reasons) + "."
