"""Editor-adapter contract, unified timeline model and editing router."""

from app.editing.adapter import (
    AdapterCapabilities,
    EditorAdapter,
    EditorOperation,
    execute_operation,
)
from app.editing.converters import ConversionResult, TimelineConverter, UnsupportedElement
from app.editing.timeline import Project

__all__ = [
    "AdapterCapabilities",
    "ConversionResult",
    "EditorAdapter",
    "EditorOperation",
    "Project",
    "TimelineConverter",
    "UnsupportedElement",
    "execute_operation",
]
