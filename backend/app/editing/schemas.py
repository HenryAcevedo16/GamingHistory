from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RouterOperation = Literal[
    "auto_assembly",
    "editable_draft",
    "professional_edit",
    "transcript_edit",
]


class RouterCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    name: str
    eligible: bool
    selected: bool = False
    reason: str
    enabled: bool
    installed: bool
    connected: bool
    adapter_registered: bool
    pricing: str
    missing_capabilities: list[str] = Field(default_factory=list)


class RouterSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    name: str
    reason: str
    score: int
    adapter_registered: bool
    executable: bool


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    label: str
    description: str
    required_capabilities: list[str]
    adapter_operation: str
    capability_source: str
    selected: RouterSelection | None = None
    candidates: list[RouterCandidate] = Field(default_factory=list)
    discarded: list[RouterCandidate] = Field(default_factory=list)
    explanation: str
    generated_at: datetime


class RouterDecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: RouterOperation
    manual_plugin_id: str | None = None
    cloud_authorized: bool = False
    required_capabilities: list[str] | None = None
    preferred_plugin_id: str | None = None


class RouterDecisionsResponse(BaseModel):
    cloud_authorized: bool
    decisions: list[RouterDecision]
    generated_at: datetime
