from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from olly.dashboard.routes import router

DASHBOARD_DIR = Path(__file__).parent

app = FastAPI(title="Olly Dashboard")
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR / "static"), name="static")
app.include_router(router)

templates = Jinja2Templates(directory=DASHBOARD_DIR / "templates")
