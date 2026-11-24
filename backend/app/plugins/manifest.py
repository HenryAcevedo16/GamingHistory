"""Pydantic schema for plugin manifests.

A manifest is the only thing a plugin needs to provide. The core validates it
and drives the UI + diagnostics from these declarations, so adding a plugin
never requires touching the core.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConnectionType = Literal[
    "local-binary", "local-bridge", "mcp-stdio", "mcp-http", "cloud-api"
]
InstallStatus = Literal["not_installed", "installed", "connected", "disabled", "error"]
RiskLevel = Literal["low", "medium", "high"]
CheckKind = Literal["binary", "file", "env", "tcp", "http", "command"]
CapabilityStatus = Literal["declared", "verified", "unsupported"]
PricingModel = Literal["free", "freemium", "paid", "unknown"]


class PluginRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str
    kind: Literal["binary", "software", "endpoint", "python", "account", "env"]
    identifier: str
    optional: bool = False
    notes: str | None = None
    check_id: str | None = None


class PluginPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    risk: RiskLevel = "low"
    requires_confirmation: bool = True


class PluginTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    destructive: bool = False


class PluginCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str | None = None
    status: CapabilityStatus = "declared"


class KnownCosts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing: PricingModel = "unknown"
    currency: str | None = None
    notes: str = ""
    limits: str | None = None


class DiagnosticCheck(BaseModel):
    """A real probe executed by the core. Nothing here is simulated.

    `target` supports `${ENV_VAR|default}` and OS env vars (e.g. `%LOCALAPPDATA%`).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str
    kind: CheckKind
    target: str
    args: list[str] = Field(default_factory=list)
    optional: bool = False
    hint: str | None = None
    timeout_seconds: float = Field(default=10.0, ge=0.5, le=120.0)


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    version: str
    description: str
    category: str
    connection_type: ConnectionType
    mcp_command_or_endpoint: str | None = None
    requirements: list[PluginRequirement] = Field(default_factory=list)
    permissions: list[PluginPermission] = Field(default_factory=list)
    tools: list[PluginTool] = Field(default_factory=list)
    capabilities: list[PluginCapability] = Field(default_factory=list)
    known_costs: KnownCosts = Field(default_factory=KnownCosts)
    documentation_url: str | None = None
    install_status: InstallStatus = "not_installed"
    optional: bool = False
    icon: str | None = None
    accent: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    diagnostics: list[DiagnosticCheck] = Field(default_factory=list)
    require_adapter_health: bool = False
