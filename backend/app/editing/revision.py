"""Match a confirmed export to the persisted project used for preflight."""
from hashlib import sha256

from app.core.errors import InvalidOperation
from app.editing.timeline import Project


def revision(project: Project) -> str:
    return sha256(project.model_dump_json().encode()).hexdigest()


def check_revision(project: Project, expected: str | None) -> None:
    if expected is not None and revision(project) != expected:
        raise InvalidOperation("El proyecto cambió. Revisa de nuevo el envío.", status_code=409)
