from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_manager
from app.editing.router import EditingRouter
from app.editing.schemas import (
    RouterDecideRequest,
    RouterDecision,
    RouterDecisionsResponse,
)
from app.plugins.manager import PluginManager

router = APIRouter(prefix="/router", tags=["router"])


@router.get("/decisions", response_model=RouterDecisionsResponse)
def list_decisions(
    cloud_authorized: bool = Query(default=False),
    manual_plugin_id: str | None = Query(default=None),
    manager: PluginManager = Depends(get_manager),
) -> RouterDecisionsResponse:
    editing_router = EditingRouter(manager.list_views())
    decisions = editing_router.decide_all(
        cloud_authorized=cloud_authorized,
        manual_plugin_id=manual_plugin_id,
    )
    return RouterDecisionsResponse(
        cloud_authorized=cloud_authorized,
        decisions=decisions,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/decide", response_model=RouterDecision)
def decide(
    payload: RouterDecideRequest,
    manager: PluginManager = Depends(get_manager),
) -> RouterDecision:
    editing_router = EditingRouter(manager.list_views())
    return editing_router.decide(
        payload.operation,
        manual_plugin_id=payload.manual_plugin_id,
        cloud_authorized=payload.cloud_authorized,
        required_capabilities=payload.required_capabilities,
        preferred_plugin_id=payload.preferred_plugin_id,
    )
