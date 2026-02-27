from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from olly.dashboard.api_routes import router as api_router

DASHBOARD_DIR = Path(__file__).parent
DIST_DIR = DASHBOARD_DIR / "static" / "dist"

app = FastAPI(title="Olly Dashboard")
app.include_router(api_router)

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_catchall(full_path: str):
        return FileResponse(DIST_DIR / "index.html")
