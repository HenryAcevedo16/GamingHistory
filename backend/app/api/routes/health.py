from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import get_manager
from app.core.config import settings
from app.plugins.manager import PluginManager
from app.plugins.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(manager: PluginManager = Depends(get_manager)) -> HealthResponse:
    views = manager.list_views()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=__version__,
        database="ok",
        plugins_dir=str(settings.resolved_plugins_dir),
        plugins_found=len(views),
        manifest_errors=len(manager.snapshot.issues),
        details={
            "counts": manager.counts(views).model_dump(),
            "manifest_errors": [
                {"path": issue.path, "error": issue.error} for issue in manager.snapshot.issues
            ],
        },
    )
