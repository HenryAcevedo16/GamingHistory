from __future__ import annotations

import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path

from app.backup.format import BackupError, DISK_RESERVE
from app.core.config import PROJECT_ROOT, settings


def clean_path(value: str | Path) -> Path:
    raw = str(value)
    path = Path(raw)
    if (not raw or not path.is_absolute() or ".." in path.parts or "\x00" in raw
            or (os.name == "nt" and (raw.startswith(("\\\\", "//"))
                or any(":" in part or part.endswith((".", " ")) for part in path.parts[1:])))):
        raise BackupError("Usa una ruta local absoluta, sin '..' ni rutas especiales.")
    return path


def without_links(path: Path) -> None:
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackupError("No se admiten enlaces simbólicos ni puntos de reanálisis.")


def destination_path(value: str | Path) -> Path:
    path = clean_path(value)
    without_links(path)
    path = clean_path(path.resolve())
    protected = (PROJECT_ROOT, settings.workspace_dir.expanduser().resolve())
    # Also reject their ancestors: don't treat a drive or a broad parent as a backup folder.
    if path == path.parent or any(path.is_relative_to(p) or p.is_relative_to(path) for p in protected):
        raise BackupError("El destino debe estar separado del repositorio y del workspace.")
    if os.name == "nt":
        from ctypes import windll

        if windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise BackupError("El destino debe estar en un disco local, no en una unidad de red.")
        system = [Path(path.anchor) / name for name in (
            "Windows", "Program Files", "Program Files (x86)", "ProgramData",
            "System Volume Information", "$Recycle.Bin", "Recovery", "Boot", "EFI",
        )]
        system += [Path(path.anchor) / "Users" / name for name in ("Default", "Public", "All Users")]
        system += [Path(value).resolve() for key in (
            "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "ALLUSERSPROFILE",
        ) if (value := os.environ.get(key))]
    else:
        system = [Path("/") / name for name in (
            "bin", "boot", "dev", "etc", "lib", "lib64", "proc", "root", "run",
            "sbin", "sys", "usr", "var", "System", "Library", "private",
        )]
    if any(path.is_relative_to(p) for p in system):
        raise BackupError("El destino no puede ser una carpeta del sistema.")
    return path


def workspace_file(value: str) -> Path:
    root = settings.resolved_workspace_dir
    relative = Path(value)
    if relative.anchor and not relative.is_absolute():
        raise BackupError("Ruta de recurso inválida.")
    path = clean_path(root / relative)
    if not path.is_relative_to(root) or path == root:
        raise BackupError("La ruta del recurso sale de GHS_WORKSPACE_DIR.")
    without_links(path)
    return path


@contextmanager
def read_file(path: Path, *, single_link: bool = False):
    without_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or (single_link and before.st_nlink != 1):
        raise BackupError("Solo se permiten archivos regulares sin enlaces en el respaldo.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as source:
        without_links(path)
        if not os.path.samestat(os.fstat(fd), before) or not os.path.samestat(path.lstat(), before):
            raise BackupError("El archivo cambió mientras se abría.")
        yield source


def disk_space(root: Path, size: int = 0) -> int:
    without_links(root)
    free = shutil.disk_usage(root).free
    if size and free < size + DISK_RESERVE:
        raise BackupError("No hay espacio libre suficiente en disco.", code="BACKUP_NO_SPACE")
    return free
