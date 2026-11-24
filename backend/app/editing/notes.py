"""Canonical, plain-text notes shared by projects, imports and backups."""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, Field, StrictStr

MAX_NOTE_CHARS = 500


def sanitize_note(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " "))
    return "".join(c for c in value if c == "\n" or not unicodedata.category(c).startswith("C")).strip()


def canonical_note(value: str) -> str:
    if not value or sanitize_note(value) != value:
        raise ValueError("La nota del respaldo no es texto saneado.")
    return value


NoteText = Annotated[StrictStr, Field(max_length=MAX_NOTE_CHARS)]
BackupNote = Annotated[NoteText, AfterValidator(canonical_note)]
