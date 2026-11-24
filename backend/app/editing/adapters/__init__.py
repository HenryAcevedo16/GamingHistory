"""Concrete adapters are loaded here, outside the editing core."""

from importlib import import_module
from pkgutil import iter_modules

for module in iter_modules(__path__):
    if not module.name.startswith("_"):
        import_module(f"{__name__}.{module.name}")
