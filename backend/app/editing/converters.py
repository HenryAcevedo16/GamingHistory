"""Unified-timeline converters (base contract only).

Concrete converters (CapCut, DaVinci Resolve, FFmpeg, OTIO/EDL/FCPXML) arrive
in later phases. Their non-negotiable obligation is to report every element
they could not export instead of dropping it silently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.editing.timeline import Project


class UnsupportedElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: str
    reason: str
    element_id: str | None = None


class ConversionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    supported: bool
    exported: list[str] = Field(default_factory=list)
    unsupported: list[UnsupportedElement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    payload: dict[str, Any] | None = None

    @property
    def complete(self) -> bool:
        return self.supported and not self.unsupported


class TimelineConverter(ABC):
    """Unified Project -> a specific editor or interchange format."""

    @property
    @abstractmethod
    def target(self) -> str:
        """Stable target id, e.g. 'ffmpeg', 'capcut', 'resolve', 'otio'."""

    @abstractmethod
    def convert(self, project: Project) -> ConversionResult:
        """Convert the project and report anything that could not be exported."""
