from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import (
    DependencyUnavailable,
    PermissionsNotAcknowledged,
    PluginDisabled,
    PluginNotFound,
    PluginNotInstalled,
)
from app.models.audit import AuditLog
from app.models.plugin import PluginState, utcnow
from app.plugins.diagnostics import DiagnosticReport, run_checks
from app.plugins.manifest import PluginManifest
from app.plugins.registry import load_registry
from app.plugins.schemas import (
    AuditEntry,
    CapabilityListResponse,
    DiagnosisSummary,
    PluginCounts,
    PluginView,
    RequirementReport,
    RequirementStatus,
    ToolListResponse,
)

INSTALLED_STATUSES = {"installed", "connected"}
LIVE_CHECK_KINDS = {"binary", "command", "tcp", "http"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PluginManager:
    """Manifest-driven plugin lifecycle.

    Every state change that claims an integration works is preceded by a real
    diagnostic run. Failures surface as structured errors, never as success.
    """

    def __init__(self, session: Session, plugins_dir: Path | None = None) -> None:
        self.session = session
        self.snapshot = load_registry(plugins_dir or settings.resolved_plugins_dir)

    # -- internals ---------------------------------------------------------

    def _manifest(self, plugin_id: str) -> PluginManifest:
        manifest = self.snapshot.manifests.get(plugin_id)
        if manifest is None:
            raise PluginNotFound(f"No existe un plugin con id '{plugin_id}'.")
        return manifest

    def _state(self, manifest: PluginManifest, *, create: bool = False) -> PluginState:
        state = self.session.get(PluginState, manifest.id)
        if state is not None:
            return state
        state = PluginState(
            plugin_id=manifest.id,
            install_status=manifest.install_status,
            enabled=True,
            connected=False,
        )
        if create:
            self.session.add(state)
            self.session.commit()
            self.session.refresh(state)
        return state

    def _persist(self, state: PluginState) -> PluginState:
        state.updated_at = utcnow()
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        return state

    def _audit(self, plugin_id: str, action: str, status: str, detail: str = "") -> None:
        self.session.add(
            AuditLog(plugin_id=plugin_id, action=action, status=status, detail=detail[:2000])
        )
        self.session.commit()

    def _display_status(self, state: PluginState) -> str:
        if state.install_status == "error":
            return "error"
        if not state.enabled:
            return "disabled"
        if state.connected:
            return "connected"
        if state.install_status in INSTALLED_STATUSES:
            return "installed"
        return "available"

    def _view(self, manifest: PluginManifest, state: PluginState) -> PluginView:
        diagnosis = None
        if state.last_diagnosis_at is not None:
            diagnosis = DiagnosisSummary(
                ran_at=state.last_diagnosis_at, ok=state.last_diagnosis_ok
            )
        return PluginView(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            category=manifest.category,
            connection_type=manifest.connection_type,
            mcp_command_or_endpoint=manifest.mcp_command_or_endpoint,
            icon=manifest.icon,
            accent=manifest.accent,
            optional=manifest.optional,
            documentation_url=manifest.documentation_url,
            install_status=state.install_status,
            enabled=state.enabled,
            connected=state.connected,
            display_status=self._display_status(state),
            installed_at=state.installed_at,
            connected_at=state.connected_at,
            last_error=state.last_error,
            last_diagnosis=diagnosis,
            checks_total=len(manifest.diagnostics),
            requirements=manifest.requirements,
            permissions=manifest.permissions,
            tools=manifest.tools,
            capabilities=manifest.capabilities,
            known_costs=manifest.known_costs,
            diagnostics=manifest.diagnostics,
        )

    def _run_diagnostics(self, manifest: PluginManifest, state: PluginState) -> DiagnosticReport:
        report = run_checks(
            manifest.id,
            manifest.diagnostics,
            default_timeout=settings.command_timeout_seconds,
        )
        state.last_diagnosis_at = report.ran_at
        state.last_diagnosis_ok = report.ok
        self._persist(state)
        return report

    def _failing_checks(self, report: DiagnosticReport) -> list[dict[str, str]]:
        return [
            {"id": check.id, "label": check.label, "evidence": check.evidence, "hint": check.hint or ""}
            for check in report.checks
            if check.status == "fail"
        ]

    # -- reads -------------------------------------------------------------

    def list_views(self) -> list[PluginView]:
        views = [
            self._view(manifest, self._state(manifest))
            for manifest in self.snapshot.manifests.values()
        ]
        return sorted(views, key=lambda item: item.name.lower())

    def counts(self, views: list[PluginView]) -> PluginCounts:
        counts = PluginCounts(total=len(views))
        for view in views:
            if view.display_status in ("available", "installed", "connected", "disabled", "error"):
                setattr(counts, view.display_status, getattr(counts, view.display_status) + 1)
        return counts

    def get_view(self, plugin_id: str) -> PluginView:
        manifest = self._manifest(plugin_id)
        return self._view(manifest, self._state(manifest))

    def get_tools(self, plugin_id: str) -> ToolListResponse:
        manifest = self._manifest(plugin_id)
        return ToolListResponse(
            plugin_id=manifest.id,
            note=(
                "Herramientas declaradas por el manifiesto. En la Fase 1 no existe "
                "adaptador ejecutable todavía: no hay verificación de ejecución."
            ),
            tools=manifest.tools,
        )

    def get_capabilities(self, plugin_id: str) -> CapabilityListResponse:
        manifest = self._manifest(plugin_id)
        return CapabilityListResponse(
            plugin_id=manifest.id,
            note=(
                "Capacidades declaradas en el manifiesto. El estado 'declared' significa "
                "que aún no fueron verificadas mediante una operación real (Fase 2+)."
            ),
            capabilities=manifest.capabilities,
        )

    def audit_entries(self, plugin_id: str, limit: int = 50) -> list[AuditEntry]:
        self._manifest(plugin_id)
        rows = self.session.exec(
            select(AuditLog)
            .where(AuditLog.plugin_id == plugin_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        ).all()
        return [
            AuditEntry(
                id=row.id or 0,
                plugin_id=row.plugin_id,
                action=row.action,
                status=row.status,
                detail=row.detail,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # -- actions -----------------------------------------------------------

    def install(self, plugin_id: str, *, confirm_permissions: bool) -> tuple[PluginView, str]:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)

        if state.install_status in INSTALLED_STATUSES and state.installed_at is not None:
            message = "El plugin ya está instalado."
            if not state.enabled:
                state.enabled = True
                state.connected = False
                self._persist(state)
                message = "El plugin ya estaba instalado; se reactivó."
            self._audit(plugin_id, "install", "ok", message)
            return self._view(manifest, state), message

        pending = [permission for permission in manifest.permissions if permission.requires_confirmation]
        if pending and not confirm_permissions:
            self._audit(
                plugin_id,
                "install",
                "denied",
                "Permisos pendientes de confirmación: " + ", ".join(p.id for p in pending),
            )
            raise PermissionsNotAcknowledged(
                "Debes confirmar los permisos del plugin antes de instalarlo.",
                details=[permission.model_dump() for permission in pending],
            )

        if not manifest.diagnostics:
            raise DependencyUnavailable(
                "El manifiesto no declara comprobaciones de diagnóstico; "
                "no es posible verificar la instalación."
            )

        report = self._run_diagnostics(manifest, state)
        if not report.ok:
            failing = self._failing_checks(report)
            state.last_error = (
                "Diagnóstico fallido: " + "; ".join(item["label"] for item in failing)
            )
            self._persist(state)
            self._audit(plugin_id, "install", "error", state.last_error)
            raise DependencyUnavailable(
                "No se puede instalar: faltan dependencias verificables.",
                details={"checks": failing, "summary": report.summary},
            )

        state.install_status = "installed"
        state.installed_at = _now()
        state.enabled = True
        state.last_error = None
        self._persist(state)
        self._audit(
            plugin_id,
            "install",
            "ok",
            f"Instalado tras verificar {report.summary['passed']} comprobaciones reales.",
        )
        return self._view(manifest, state), "Plugin instalado y dependencias verificadas."

    def connect(self, plugin_id: str) -> tuple[PluginView, str]:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)

        if state.install_status not in INSTALLED_STATUSES or state.installed_at is None:
            raise PluginNotInstalled(
                "El plugin debe instalarse antes de conectarse.", details={"plugin_id": plugin_id}
            )
        if not state.enabled:
            raise PluginDisabled(
                "El plugin está desactivado. Actívalo antes de conectar.",
                details={"plugin_id": plugin_id},
            )
        if not manifest.diagnostics:
            raise DependencyUnavailable("No hay comprobaciones para verificar la conexión.")

        report = self._run_diagnostics(manifest, state)
        if not report.ok:
            failing = self._failing_checks(report)
            state.connected = False
            state.connected_at = None
            state.last_error = (
                "Conexión rechazada: " + "; ".join(item["label"] for item in failing)
            )
            self._persist(state)
            self._audit(plugin_id, "connect", "error", state.last_error)
            raise DependencyUnavailable(
                "No se pudo conectar: el diagnóstico real falló.",
                details={"checks": failing, "summary": report.summary},
            )

        live_channel = any(
            check.status == "pass" and not check.optional and check.kind in LIVE_CHECK_KINDS
            for check in report.checks
        )
        if not live_channel:
            state.connected = False
            state.connected_at = None
            state.last_error = (
                "No se verificó ningún canal activo (binario, comando, TCP o HTTP)."
            )
            self._persist(state)
            self._audit(plugin_id, "connect", "error", state.last_error)
            raise DependencyUnavailable(
                "No se puede marcar como conectado: el diagnóstico solo confirmó "
                "archivos o variables, no un canal de ejecución real.",
                details={
                    "checks": [check.model_dump() for check in report.checks],
                    "live_check_kinds": sorted(LIVE_CHECK_KINDS),
                },
            )

        state.connected = True
        state.connected_at = _now()
        state.last_error = None
        self._persist(state)
        self._audit(
            plugin_id,
            "connect",
            "ok",
            f"Conexión verificada con {report.summary['passed']} comprobaciones reales.",
        )
        return self._view(manifest, state), "Conexión verificada."

    def disconnect(self, plugin_id: str) -> tuple[PluginView, str]:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)
        if state.connected:
            state.connected = False
            state.connected_at = None
            self._persist(state)
            self._audit(plugin_id, "disconnect", "ok", "Plugin desconectado.")
            message = "Plugin desconectado."
        else:
            self._audit(plugin_id, "disconnect", "ok", "Sin conexión activa (no-op).")
            message = "El plugin no estaba conectado."
        return self._view(manifest, state), message

    def set_enabled(self, plugin_id: str, enabled: bool) -> tuple[PluginView, str]:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)
        state.enabled = enabled
        if not enabled:
            state.connected = False
            state.connected_at = None
        self._persist(state)
        action = "enable" if enabled else "disable"
        self._audit(plugin_id, action, "ok", "Activado." if enabled else "Desactivado.")
        message = "Plugin activado." if enabled else "Plugin desactivado y desconectado."
        return self._view(manifest, state), message

    def diagnose(self, plugin_id: str) -> DiagnosticReport:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)
        report = self._run_diagnostics(manifest, state)

        if not report.ok and state.connected:
            failing = self._failing_checks(report)
            state.connected = False
            state.connected_at = None
            state.last_error = (
                "Diagnóstico fallido; conexión cerrada: "
                + "; ".join(item["label"] for item in failing)
            )
            self._persist(state)
        elif report.ok:
            state.last_error = None
            self._persist(state)

        status = "ok" if report.ok else "warn"
        self._audit(
            plugin_id,
            "diagnose",
            status,
            f"{report.summary['passed']} ok / {report.summary['failed']} fallos / "
            f"{report.summary['warnings']} avisos / {report.summary['skipped']} omitidas.",
        )
        return report

    def verify_requirements(self, plugin_id: str) -> RequirementReport:
        manifest = self._manifest(plugin_id)
        state = self._state(manifest, create=True)
        report = self._run_diagnostics(manifest, state)
        by_id = {check.id: check for check in report.checks}

        requirements: list[RequirementStatus] = []
        for requirement in manifest.requirements:
            check = by_id.get(requirement.check_id) if requirement.check_id else None
            requirements.append(
                RequirementStatus(
                    id=requirement.id,
                    label=requirement.label,
                    kind=requirement.kind,
                    identifier=requirement.identifier,
                    optional=requirement.optional,
                    check_id=requirement.check_id,
                    satisfied=(check.status == "pass") if check else None,
                    check_status=check.status if check else None,
                    evidence=check.evidence if check else "Sin comprobación vinculada.",
                    notes=requirement.notes,
                )
            )

        return RequirementReport(
            plugin_id=manifest.id,
            ok=report.ok,
            requirements=requirements,
            checks=report.checks,
            ran_at=report.ran_at,
        )
