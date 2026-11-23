"""Test-only adapter.

This module lives exclusively under `tests/`. It is never imported by the app
and never registered in the production registry.
"""

from __future__ import annotations

from typing import Any

from app.editing.adapter import AdapterCapabilities, EditorAdapter, EditorOperation


class DummyAdapter(EditorAdapter):
    def __init__(
        self,
        plugin_id: str = "dummy",
        operations: set[EditorOperation] | None = None,
    ) -> None:
        super().__init__(plugin_id)
        self._operations = operations or set()
        self.capability_calls = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_capabilities(self) -> AdapterCapabilities:
        self.capability_calls += 1
        return AdapterCapabilities(operations=set(self._operations), verified=False)

    def connect(self) -> None:
        self.calls.append(("connect", {}))
        self._operations.add(EditorOperation.CONNECT)

    def create_timeline(self, project_id: str, name: str, **options: Any) -> dict[str, Any]:
        self.calls.append(
            ("create_timeline", {"project_id": project_id, "name": name, **options})
        )
        return {"id": "timeline-1", "project_id": project_id, "name": name}

    def render_preview(self, timeline_id: str, **options: Any) -> dict[str, Any]:
        self.calls.append(("render_preview", {"timeline_id": timeline_id, **options}))
        return {"job_id": "job-1", "status": "queued"}
