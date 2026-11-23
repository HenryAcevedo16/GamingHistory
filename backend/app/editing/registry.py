"""Plugin-id → adapter-class registry.

The core never imports a concrete adapter. A new integration registers itself
(`register_adapter("my-plugin")`) and the rest of the app keeps working without
changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.errors import AdapterNotRegistered
from app.editing.adapter import EditorAdapter

AdapterFactory = Callable[[str], EditorAdapter]


@dataclass
class AdapterRegistry:
    _factories: dict[str, AdapterFactory] = field(default_factory=dict)

    def register(
        self, plugin_id: str, factory: AdapterFactory, *, replace: bool = False
    ) -> None:
        if not plugin_id:
            raise ValueError("plugin_id no puede estar vacío.")
        if plugin_id in self._factories and not replace:
            raise ValueError(f"Ya hay un adaptador registrado para '{plugin_id}'.")
        self._factories[plugin_id] = factory

    def decorator(self, plugin_id: str):
        def register(factory: AdapterFactory) -> AdapterFactory:
            self.register(plugin_id, factory)
            return factory

        return register

    def has(self, plugin_id: str) -> bool:
        return plugin_id in self._factories

    def plugin_ids(self) -> list[str]:
        return sorted(self._factories)

    def create(self, plugin_id: str) -> EditorAdapter:
        factory = self._factories.get(plugin_id)
        if factory is None:
            raise AdapterNotRegistered(
                f"No hay adaptador registrado para el plugin '{plugin_id}'.",
                details={"plugin_id": plugin_id, "registered": self.plugin_ids()},
            )
        adapter = factory(plugin_id)
        if not isinstance(adapter, EditorAdapter):
            raise TypeError(
                f"La fábrica de '{plugin_id}' no devolvió un EditorAdapter."
            )
        return adapter


default_registry = AdapterRegistry()


def register_adapter(plugin_id: str):
    """Decorator used by concrete adapters (Phase 3+)."""
    return default_registry.decorator(plugin_id)
