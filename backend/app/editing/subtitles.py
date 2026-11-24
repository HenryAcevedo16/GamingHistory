"""Parse strict SRT into the existing validated subtitle timeline model."""
from __future__ import annotations

import re

from app.editing.timeline import SubtitleCue, SubtitleTrack

_TIME = r"[0-9]{2}:[0-5][0-9]:[0-5][0-9],[0-9]{3}"
_RANGE = re.compile(rf"({_TIME}) --> ({_TIME})")


def _milliseconds(value: str) -> int:
    hours, minutes, seconds, milliseconds = map(int, re.split("[:,]", value))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def parse_srt(text: str) -> list[SubtitleCue]:
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    cues = []
    for index, block in enumerate(re.split(r"\n[ \t]*\n", normalized), start=1):
        lines = block.split("\n")
        timing = _RANGE.fullmatch(lines[1]) if len(lines) >= 3 else None
        if not timing or lines[0] != str(index) or not all(line.strip() for line in lines[2:]):
            raise ValueError("Bloque SRT inválido.")
        start, end = map(_milliseconds, timing.groups())
        if cues and start < round((cues[-1].start_seconds + cues[-1].duration_seconds) * 1000):
            raise ValueError("Los bloques SRT deben estar ordenados y no solaparse.")
        cues.append(SubtitleCue(start_seconds=start / 1000, duration_seconds=(end - start) / 1000,
                                text="\n".join(lines[2:])))
    return SubtitleTrack(name="Subtítulos", cues=cues).cues
