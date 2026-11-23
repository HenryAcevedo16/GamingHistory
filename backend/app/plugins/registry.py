from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.plugins.manifest import PluginManifest


@dataclass
class ManifestIssue:
    path: str
    error: str


@dataclass
class RegistrySnapshot:
    manifests: dict[str, PluginManifest] = field(default_factory=dict)
    issues: list[ManifestIssue] = field(default_factory=list)
    scanned_dirs: int = 0

    @property
    def plugin_count(self) -> int:
        return len(self.manifests)


def _read_manifest(path: Path) -> PluginManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Manifest root must be a JSON object.")
    return PluginManifest.model_validate(raw)


def load_registry(plugins_dir: Path) -> RegistrySnapshot:
    snapshot = RegistrySnapshot()
    if not plugins_dir.is_dir():
        snapshot.issues.append(
            ManifestIssue(path=str(plugins_dir), error="Plugins directory does not exist.")
        )
        return snapshot

    for folder in sorted(p for p in plugins_dir.iterdir() if p.is_dir()):
        manifest_path = folder / "manifest.json"
        snapshot.scanned_dirs += 1
        if not manifest_path.is_file():
            snapshot.issues.append(
                ManifestIssue(path=str(folder), error="Missing manifest.json")
            )
            continue
        try:
            manifest = _read_manifest(manifest_path)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ()))
            snapshot.issues.append(
                ManifestIssue(
                    path=str(manifest_path),
                    error=f"{location or 'manifest'}: {first.get('msg', 'invalid')}",
                )
            )
            continue
        except (OSError, ValueError) as exc:
            snapshot.issues.append(ManifestIssue(path=str(manifest_path), error=str(exc)))
            continue

        if manifest.id in snapshot.manifests:
            snapshot.issues.append(
                ManifestIssue(
                    path=str(manifest_path),
                    error=f"Duplicate plugin id '{manifest.id}' (already declared elsewhere).",
                )
            )
            continue

        snapshot.manifests[manifest.id] = manifest

    return snapshot
