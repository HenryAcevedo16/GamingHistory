from __future__ import annotations

import io
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from app.backup.format import ASSET_NAME, BACKUP_ID, MANIFEST, METADATA, TIMELINE, BackupError, Manifest, check_file
from app.backup.paths import destination_path, disk_space, read_file, without_links


@dataclass(frozen=True)
class DestinationState:
    location: str
    free_bytes: int


class BackupDestination(Protocol):
    def state(self, required_bytes: int = 0) -> DestinationState: ...
    def list(self) -> list[str]: ...
    def save(self, manifest: Manifest, sources: dict[str, bytes | Path]) -> None: ...
    def read(self, backup_id: str, name: str) -> AbstractContextManager[BinaryIO]: ...


class LocalDestination:
    def __init__(self, value: str | Path) -> None:
        self.root = destination_path(value)

    def prepare(self) -> None:
        without_links(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        without_links(self.root)
        # An actual exclusive write checks permissions (including Windows ACLs).
        with tempfile.TemporaryFile(dir=self.root) as probe:
            probe.write(b"\0")
            probe.flush()

    def state(self, required_bytes: int = 0) -> DestinationState:
        without_links(self.root)
        if not self.root.is_dir():
            raise BackupError("La carpeta de respaldo no existe o no es un directorio.")
        return DestinationState(str(self.root), disk_space(self.root, required_bytes))

    def list(self) -> list[str]:
        self.state()
        return sorted((path.name for path in self.root.iterdir()
                       if BACKUP_ID.fullmatch(path.name)), reverse=True)

    def _folder(self, backup_id: str) -> Path:
        if not BACKUP_ID.fullmatch(backup_id):
            raise BackupError("ID de respaldo inválido.")
        folder = self.root / backup_id
        without_links(folder)
        return folder

    def read(self, backup_id: str, name: str) -> AbstractContextManager[BinaryIO]:
        if name not in {MANIFEST, METADATA, TIMELINE} and not ASSET_NAME.fullmatch(name):
            raise BackupError("Nombre de archivo de respaldo inválido.")
        return read_file(self._folder(backup_id) / name, single_link=True)

    def save(self, manifest: Manifest, sources: dict[str, bytes | Path]) -> None:
        folder = self._folder(manifest.id)
        document = manifest.model_dump_json().encode("utf-8")
        self.state(sum(entry.size for entry in manifest.files) + len(document))
        try:
            folder.mkdir(mode=0o700)
        except FileExistsError:
            raise BackupError("Ya existe un respaldo con ese ID; no se sobrescribió.",
                              code="BACKUP_EXISTS", status_code=409) from None
        owned: list[Path] = []
        try:
            for entry in manifest.files:
                source = sources[entry.name]
                target = folder / entry.name
                with (io.BytesIO(source) if isinstance(source, bytes) else read_file(source, single_link=True)) as stream:
                    without_links(folder)
                    with target.open("xb") as output:
                        owned.append(target)
                        check_file(stream, entry, output)
            # Publish the manifest last. A crash leaves an incomplete backup, never a valid one.
            without_links(folder)
            with (folder / MANIFEST).open("xb") as output:
                owned.append(folder / MANIFEST)
                output.write(document)
        except Exception:
            cleanup(folder, owned)
            raise


def cleanup(folder: Path, files: list[Path]) -> None:
    try:
        without_links(folder)
        for path in reversed(files):
            path.unlink(missing_ok=True)
        folder.rmdir()
    except (OSError, BackupError):
        # Don't follow a moved directory or remove unrecognized files.
        pass
