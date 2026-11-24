"""Single mapping from executable operations to declared capability ids.

Both the Plugin Manager and the Editing Router need this answer, and they used
to carry private copies that drifted (the router's copy only knew FFmpeg's
capability names). One table keeps them honest.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.editing.adapter import EditorOperation

OPERATION_CAPABILITIES: dict[EditorOperation, frozenset[str]] = {
    EditorOperation.HEALTH_CHECK: frozenset({"project.inspect"}),
    EditorOperation.IMPORT_MEDIA: frozenset({"media.inspect", "media.import"}),
    EditorOperation.CREATE_PROJECT: frozenset({"draft.create"}),
    EditorOperation.CREATE_TIMELINE: frozenset({"media.cut", "media.concat", "timeline.create"}),
    EditorOperation.ADD_TRACK: frozenset({"track.add"}),
    EditorOperation.ADD_CLIP: frozenset({"clip.add"}),
    EditorOperation.ADD_SUBTITLES: frozenset({"subtitle.add"}),
    EditorOperation.ADD_AUDIO: frozenset({"audio.mix"}),
    EditorOperation.RENDER_PREVIEW: frozenset({"render.final", "render"}),
    EditorOperation.RENDER_FINAL: frozenset({"render.final", "audio.mix", "render"}),
    EditorOperation.EXPORT_PROJECT: frozenset({"render.final"}),
    EditorOperation.GET_JOB_STATUS: frozenset({"job.status"}),
}


def capabilities_for_operations(operations: Iterable[EditorOperation]) -> set[str]:
    """Capability ids backed by at least one executable operation."""
    available: set[str] = set()
    for operation in operations:
        available.update(OPERATION_CAPABILITIES.get(operation, frozenset()))
    return available
