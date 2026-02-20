from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from prefab_ui.actions import SetState
from prefab_ui.app import PrefabApp
from prefab_ui.components import Button, Column, H1, Page, Pages, Row

from olly.dashboard_prefab.pages import (
    build_dashboard_page,
    build_dbt_page,
    build_table_detail_page,
    build_tables_page,
    build_usage_page,
)
from olly.dashboard_prefab.state import build_initial_state


def create_app() -> FastAPI:
    """Create FastAPI app serving the Prefab dashboard."""
    app = FastAPI(title="Olly Prefab Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def root():
        prefab_app = build_prefab_app()
        return prefab_app.html()

    return app


def build_navigation():
    """Build the navigation bar."""
    with Row(gap=2, css_class="mb-6 border-b pb-4") as nav:
        Button(
            "Dashboard",
            variant="ghost",
            on_click=SetState("page", "dashboard"),
        )
        Button(
            "Tables",
            variant="ghost",
            on_click=SetState("page", "tables"),
        )
        Button(
            "Usage & Cost",
            variant="ghost",
            on_click=SetState("page", "usage"),
        )
        Button(
            "DBT",
            variant="ghost",
            on_click=SetState("page", "dbt"),
        )
    return nav


def build_view():
    """Build the main component tree."""
    with Column(gap=4, padding=6, css_class="max-w-7xl mx-auto") as root:
        # Title
        H1("Olly Data Quality Dashboard")

        # Navigation
        build_navigation()

        # Pages
        with Pages(name="page", default_value="dashboard"):
            with Page("Dashboard", value="dashboard"):
                build_dashboard_page()

            with Page("Tables", value="tables"):
                build_tables_page()

            with Page("Table Detail", value="table_detail"):
                build_table_detail_page()

            with Page("Usage & Cost", value="usage"):
                build_usage_page()

            with Page("DBT Results", value="dbt"):
                build_dbt_page()

    return root


def build_prefab_app() -> PrefabApp:
    """Build PrefabApp with initial state and view."""
    state = build_initial_state()
    view = build_view()
    return PrefabApp(view=view, state=state)


# FastAPI app instance
app = create_app()
