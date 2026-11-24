"""Incrementally parse multipart directly into a private workspace directory."""

from __future__ import annotations

import errno
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import BinaryIO

from pydantic import BaseModel, TypeAdapter
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header

from app.core.config import settings
from app.core.errors import InvalidOperation
from app.editing.media_formats import FORMATS
from app.editing.notes import MAX_NOTE_CHARS, NoteText
from app.editing.timeline import Asset

MAX_FILES = 32
CHUNK_BYTES = 64 * 1024
_RESERVED = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]", re.I)
_ESCAPED_UNSAFE = re.compile(r"%(?:[01][0-9a-f]|7f|22|2f|5c|3a)", re.I)
_NOTE = TypeAdapter(NoteText)


class UploadIssue(BaseModel):
    code: str
    message: str


class UploadResult(BaseModel):
    name: str | None = None
    ok: bool = False
    asset: Asset | None = None
    error: UploadIssue | None = None


@dataclass
class UploadEntry:
    result: UploadResult
    path: Path | None
    note: str | None = None
    has_note: bool = False


def upload_name(raw: bytes) -> str:
    try:
        name = unicodedata.normalize("NFC", raw.decode("utf-8"))
    except UnicodeDecodeError:
        name = ""
    if (not name or len(name.encode("utf-8")) > 200 or name.startswith(".") or ".." in name
        or name != name.strip().rstrip(".") or any(c in '/\\:<>|?*"' or unicodedata.category(c).startswith("C") for c in name)
        or _ESCAPED_UNSAFE.search(name) or _RESERVED.fullmatch(name.split(".")[0].rstrip())):
        raise InvalidOperation("Nombre de archivo no seguro o reservado en Windows.", code="UPLOAD_BAD_NAME")
    return name


def storage_issue(exc: OSError) -> UploadIssue:
    if exc.errno in {errno.ENOSPC, errno.EDQUOT} or getattr(exc, "winerror", None) in {39, 112}:
        return UploadIssue(code="UPLOAD_DISK_FULL", message="No hay espacio libre para guardar el archivo en el workspace.")
    return UploadIssue(code="UPLOAD_WRITE_FAILED", message="No se pudo escribir la copia en el workspace.")


class StreamingUpload:
    def __init__(self, content_type: str) -> None:
        media, params = parse_options_header(content_type)
        boundary = params.get(b"boundary", b"")
        if media != b"multipart/form-data" or not re.fullmatch(rb"[\x20-\x7e]{1,70}", boundary):
            raise InvalidOperation("Se esperaba multipart/form-data con un separador válido.", code="UPLOAD_MULTIPART")
        self.directory = Path(mkdtemp(prefix="import-", dir=settings.resolved_workspace_dir))
        self.entries: list[UploadEntry] = []
        self.parts = 0
        self.done = False
        self.keep = False
        self.file: BinaryIO | None = None
        self.path: Path | None = None
        self.parser = MultipartParser(boundary, {
            "on_part_begin": self.part_begin,
            "on_header_field": self.header_field,
            "on_header_value": self.header_value,
            "on_header_end": self.header_end,
            "on_headers_finished": self.headers_finished,
            "on_part_data": self.part_data,
            "on_part_end": self.part_end,
            "on_end": self.end,
        })

    def part_begin(self) -> None:
        self.parts += 1
        if self.parts > MAX_FILES * 2:
            raise InvalidOperation("Demasiadas partes en la subida.", code="UPLOAD_TOO_MANY")
        self.result = UploadResult()
        self.note_bytes: bytearray | None = None
        self.note_overflow = False
        self.headers: dict[bytes, bytes] = {}
        self.field = bytearray()
        self.value = bytearray()
        self.header_bytes = 0
        self.size = 0

    def header_fragment(self, dest: bytearray, data: bytes, start: int, end: int) -> None:
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise InvalidOperation("Cabeceras multipart demasiado grandes.", code="UPLOAD_MULTIPART")
        dest.extend(data[start:end])

    def header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_fragment(self.field, data, start, end)

    def header_value(self, data: bytes, start: int, end: int) -> None:
        self.header_fragment(self.value, data, start, end)

    def header_end(self) -> None:
        field = bytes(self.field).lower()
        if field in self.headers or len(self.headers) >= 16:
            raise InvalidOperation("Cabeceras multipart inválidas.", code="UPLOAD_MULTIPART")
        self.headers[field] = bytes(self.value)
        self.field.clear()
        self.value.clear()

    def headers_finished(self) -> None:
        header = self.headers.get(b"content-disposition", b"")
        disposition, params = parse_options_header(header)
        if disposition == b"form-data" and params.get(b"name") == b"note" and b"filename" not in params:
            if not self.entries or self.entries[-1].has_note:
                raise InvalidOperation("Cada nota debe seguir a su archivo.", code="UPLOAD_MULTIPART")
            self.entries[-1].has_note = True
            self.note_bytes = bytearray()
            return
        if len(self.entries) >= MAX_FILES:
            raise InvalidOperation(f"Envía como máximo {MAX_FILES} archivos por solicitud.", code="UPLOAD_TOO_MANY")
        # Reject paths before the MIME parser's legacy Windows basename handling.
        if re.search(rb"[/\\\x00-\x1f\x7f]", header):
            self.fail(UploadIssue(code="UPLOAD_BAD_NAME", message="El nombre no puede contener rutas ni caracteres de control."))
            return
        if disposition != b"form-data" or params.get(b"name") != b"files" or b"filename" not in params:
            self.fail(UploadIssue(code="UPLOAD_MULTIPART", message="Se esperaba un archivo en el campo files."))
            return
        try:
            name = upload_name(params[b"filename"])
        except InvalidOperation as exc:
            self.fail(UploadIssue(code=exc.code, message=exc.message))
            return
        self.result.name = name
        suffix = Path(name).suffix
        if suffix.lower() not in FORMATS:
            self.fail(UploadIssue(code="UPLOAD_FORMAT", message="Formato no soportado para subir."))
            return
        stem = Path(name).stem
        for index in range(MAX_FILES + 1):
            target = self.directory / (name if index == 0 else f"{stem}-{index}{suffix}")
            try:
                self.file = target.open("xb", buffering=0)
            except FileExistsError:
                continue
            except OSError as exc:
                self.fail(storage_issue(exc))
                return
            self.path = target
            return
        raise InvalidOperation("No se pudo reservar un nombre único.", code="UPLOAD_WRITE_FAILED")

    def part_data(self, data: bytes, start: int, end: int) -> None:
        if self.note_bytes is not None:
            if len(self.note_bytes) + end - start > MAX_NOTE_CHARS * 4:
                self.note_overflow = True
            if not self.note_overflow:
                self.note_bytes.extend(data[start:end])
            return
        if self.file is None:
            return
        self.size += end - start
        if self.size > settings.upload_max_bytes:
            self.fail(UploadIssue(code="UPLOAD_TOO_LARGE", message=f"El archivo supera el límite de {settings.upload_max_bytes} bytes."))
            return
        try:
            chunk = memoryview(data)[start:end]
            if self.file.write(chunk) != len(chunk):
                raise OSError(errno.ENOSPC, "short write")
        except OSError as exc:
            self.fail(storage_issue(exc))

    def close_file(self) -> None:
        if self.file is not None:
            file, self.file = self.file, None
            file.close()

    def fail(self, issue: UploadIssue) -> None:
        try:
            self.close_file()
        finally:
            if self.path is not None:
                self.path.unlink(missing_ok=True)
                self.path = None
            self.result.error = issue

    def part_end(self) -> None:
        if self.note_bytes is not None:
            entry = self.entries[-1]
            if entry.result.error is None:
                try:
                    if self.note_overflow:
                        raise ValueError
                    entry.note = _NOTE.validate_python(self.note_bytes.decode("utf-8").replace("\r\n", "\n"))
                except ValueError:
                    if entry.path is not None:
                        entry.path.unlink()
                        entry.path = None
                    entry.result.error = UploadIssue(code="UPLOAD_BAD_NOTE",
                        message=f"La nota debe ser texto UTF-8 de hasta {MAX_NOTE_CHARS} caracteres.")
            return
        try:
            self.close_file()
        except OSError as exc:
            self.fail(storage_issue(exc))
        self.entries.append(UploadEntry(self.result, self.path))
        self.path = None

    def end(self) -> None:
        self.done = True

    def cleanup(self) -> None:
        try:
            self.close_file()
        finally:
            if not self.keep:
                shutil.rmtree(self.directory)
