from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Importing the rules catalog has the side-effect of populating REGISTRY.
# Done once at app construction time so every request sees the same set
# of registered rules without races on first hit.
import app.rules.catalog  # noqa: F401
from app.api import scans as scans_routes
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cloud Cost Optimizer & Remediation Engine",
        version="0.1.0",
        description=(
            "API-first, offline analyzer for exported AWS/Azure billing files. "
            "Detects orphaned/idle resources and emits decommission CLI command strings. "
            "Never authenticates to a cloud account."
        ),
        lifespan=lifespan,
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(scans_routes.router)
    return app


app = create_app()
