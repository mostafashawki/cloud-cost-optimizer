from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cloud Cost Optimizer & Remediation Engine",
        version="0.1.0",
        description=(
            "API-first, offline analyzer for exported AWS/Azure billing files. "
            "Detects orphaned/idle resources and emits decommission CLI command strings. "
            "Never authenticates to a cloud account."
        ),
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
