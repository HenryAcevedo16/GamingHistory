from __future__ import annotations

from fastapi import Depends
from sqlmodel import Session

from app.core.config import settings
from app.core.db import get_session
from app.plugins.manager import PluginManager


def get_manager(session: Session = Depends(get_session)) -> PluginManager:
    return PluginManager(session=session, plugins_dir=settings.resolved_plugins_dir)
