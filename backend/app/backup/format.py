from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, BinaryIO, Literal

from pydantic import Field, model_validator

from app.core.errors import StudioError
from app.editing.notes import BackupNote
from app.editing.timeline import StrictModel

MANIFEST = "manifest.json"
TIMELINE = "timeline.json"
METADATA = "metadata.json"
JSON_LIMIT = 16 * 1024**2
DISK_RESERVE = 1024**2
BACKUP_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}")
ASSET_NAME = re.compile(r"asset-[0-9]{4}(?:\.[a-z0-9]{1,10})?")


class BackupError(StudioError):
    code = "BACKUP_INVALID"
    status_code = 422


class BackupFile(StrictModel):
    name: str
    size: int = Field(ge=0)
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    asset_id: str | None = None


class Manifest(StrictModel):
    schema_version: Literal[1, 2]
    id: str
    created_at: datetime
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    files: list[BackupFile] = Field(min_length=2, max_length=1002)
    asset_notes: dict[Annotated[str, Field(min_length=1)], BackupNote] | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def valid_files(self) -> Manifest:
        if (self.schema_version == 2 and self.asset_notes is None) or (
            self.schema_version == 1 and "asset_notes" in self.model_fields_set
        ):
            raise ValueError("Las notas requieren el esquema de respaldo v2.")
        names = {item.name for item in self.files}
        assets = [item.asset_id for item in self.files if item.asset_id is not None]
        if (not BACKUP_ID.fullmatch(self.id) or self.created_at.utcoffset() is None
                or len(names) != len(self.files) or len(set(assets)) != len(assets)
                or not {TIMELINE, METADATA} <= names):
            raise ValueError("Manifiesto de respaldo inválido.")
        for item in self.files:
            if item.name in {TIMELINE, METADATA}:
                if item.asset_id is not None or item.size > JSON_LIMIT:
                    raise ValueError("Entrada JSON inválida.")
            elif not ASSET_NAME.fullmatch(item.name) or not item.asset_id:
                raise ValueError("Nombre de archivo o ID de recurso inválido.")
        return self


def json_bytes(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def measure(source: BinaryIO, limit: int, output: BinaryIO | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while block := source.read(min(1024**2, limit - size + 1)):
        size += len(block)
        if size > limit:
            raise BackupError("Se superó el tamaño permitido.", code="BACKUP_SIZE_LIMIT")
        digest.update(block)
        if output is not None:
            output.write(block)
    return size, digest.hexdigest()


def check_file(source: BinaryIO, entry: BackupFile, output: BinaryIO | None = None) -> None:
    try:
        result = measure(source, entry.size, output)
    except BackupError:
        result = None
    if result != (entry.size, entry.sha256):
        raise BackupError(f"SHA-256 o tamaño no coincide: {entry.name}.",
                          code="BACKUP_HASH_MISMATCH")
