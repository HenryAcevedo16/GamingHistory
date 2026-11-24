from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import ai, backups, editing_router, exports, health, plugins, projects, renders
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import StudioError

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gaming-history-studio")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    import app.editing.adapters  # noqa: F401
    logger.info("Database ready at %s", settings.resolved_database_url)
    logger.info("Plugins directory: %s", settings.resolved_plugins_dir)
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Centro de control para editar documentales con herramientas externas "
        "mediante plugins. Fase 2: Plugin Manager, timeline unificado y enrutamiento."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(plugins.router, prefix=settings.api_prefix)
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(editing_router.router, prefix=settings.api_prefix)
app.include_router(renders.router, prefix=settings.api_prefix)
app.include_router(exports.router, prefix=settings.api_prefix)
app.include_router(backups.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)


@app.exception_handler(StudioError)
async def studio_error_handler(_: Request, exc: StudioError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())
