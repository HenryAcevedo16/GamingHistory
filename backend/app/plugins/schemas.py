from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.plugins.diagnostics import CheckResult, DiagnosticReport
from app.plugins.manifest import (
    DiagnosticCheck,
    KnownCosts,
    PluginCapability,
    PluginPermission,
    PluginRequirement,
    PluginTool,
)


class DiagnosisSummary(BaseModel):
    ran_at: datetime | None = None
    ok: bool | None = None


class PluginView(BaseModel):
    id: str
    name: str
    version: str
    description: str
    category: str
    connection_type: str
    mcp_command_or_endpoint: str | None = None
    icon: str | None = None
    accent: str | None = None
    optional: bool = False
    documentation_url: str | None = None

    install_status: str
    enabled: bool
    connected: bool
    display_status: str
    installed_at: datetime | None = None
    connected_at: datetime | None = None
    last_error: str | None = None
    last_diagnosis: DiagnosisSummary | None = None
    checks_total: int = 0

    requirements: list[PluginRequirement] = Field(default_factory=list)
    permissions: list[PluginPermission] = Field(default_factory=list)
    tools: list[PluginTool] = Field(default_factory=list)
    capabilities: list[PluginCapability] = Field(default_factory=list)
    declared_capabilities: list[PluginCapability] = Field(default_factory=list)
    verified_capabilities: list[str] = Field(default_factory=list)
    adapter_notes: list[str] = Field(default_factory=list)
    known_costs: KnownCosts
    diagnostics: list[DiagnosticCheck] = Field(default_factory=list)


class PluginCounts(BaseModel):
    total: int = 0
    available: int = 0
    installed: int = 0
    connected: int = 0
    disabled: int = 0
    error: int = 0


class ManifestErrorView(BaseModel):
    path: str
    error: str


class PluginListResponse(BaseModel):
    items: list[PluginView]
    total: int
    counts: PluginCounts
    manifest_errors: list[ManifestErrorView] = Field(default_factory=list)
    generated_at: datetime


class InstallRequest(BaseModel):
    confirm_permissions: bool = False


class ActionResponse(BaseModel):
    success: bool
    message: str
    plugin: PluginView


class ToolListResponse(BaseModel):
    plugin_id: str
    verification: str = "declared"
    note: str
    tools: list[PluginTool]


class CapabilityListResponse(BaseModel):
    plugin_id: str
    note: str
    capabilities: list[PluginCapability]
    declared_capabilities: list[PluginCapability] = Field(default_factory=list)
    verified_capabilities: list[str] = Field(default_factory=list)


class RequirementStatus(BaseModel):
    id: str
    label: str
    kind: str
    identifier: str
    optional: bool
    check_id: str | None = None
    satisfied: bool | None = None
    check_status: str | None = None
    evidence: str | None = None
    notes: str | None = None


class RequirementReport(BaseModel):
    plugin_id: str
    ok: bool
    requirements: list[RequirementStatus]
    checks: list[CheckResult]
    ran_at: datetime


class DiagnosticResponse(DiagnosticReport):
    plugin_state: PluginView


class AuditEntry(BaseModel):
    id: int
    plugin_id: str
    action: str
    status: str
    detail: str
    created_at: datetime


class AuditResponse(BaseModel):
    plugin_id: str
    entries: list[AuditEntry]


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
    plugins_dir: str
    plugins_found: int
    manifest_errors: int
    details: dict[str, Any] = Field(default_factory=dict)
