# Dashboard Development Guide

Fast API + Jinja2 web UI for Olly data quality monitoring. Read-only dashboard displaying findings, schema history, and volume trends.

## Architecture

```
routes.py      → FastAPI route handlers (/, /findings, /history, /tables, etc.)
data.py        → Data aggregation functions (stats, filtering, grouping)
charts.py      → Vega-Lite chart specifications
templates/     → Jinja2 HTML templates
  base.html    → Base layout with navigation
  *.html       → Page templates
  partials/    → HTMX partial templates for dynamic updates
static/        → CSS styles
```

## Key Principles

**Read-Only**: Dashboard reads from findings JSON and state DB only. Never writes to warehouse or modifies data.

**State-First**: All warehouse data comes from state DB (`~/.olly/<project-hash>/state.db`), not live warehouse queries. Exception: `/config` page may connect to warehouse for live schema inspection.

**Multi-Connection**: All routes accept `connection: str = Query("")` parameter. Use `_get_current_connection()` helper to resolve connection name. Pass to state DB queries.

**HTMX**: Filters and pagination use HTMX for partial page updates. Routes return full page or partials based on `HX-Request` header.

## Development Workflow

**Run Dashboard Locally**:
```bash
cd dev/
uv run python demo_dashboard.py  # Seeds demo data + launches dashboard
# Dashboard runs at http://localhost:8000
```

**Run Tests**:
```bash
uv run pytest tests/test_dashboard.py -v
uv run pytest tests/test_dashboard.py --cov=olly.dashboard --cov-report=term-missing
```

**Test Fixtures**: Use `dashboard_client` fixture which mocks `_state_db()`, `_get_current_connection()`, and `get_all_connections()` to avoid needing real config/warehouse.

## Adding a New Page

1. **Route** (`routes.py`):
   ```python
   @router.get("/newpage", response_class=HTMLResponse)
   def newpage(request: Request, connection: str = Query("")):
       conn_name = _get_current_connection(connection)
       # Load data from state DB or findings
       return templates.TemplateResponse(request, "newpage.html", {
           "connections": get_all_connections(),
           "current_connection": conn_name,
           # ... other context
       })
   ```

2. **Template** (`templates/newpage.html`):
   ```html
   {% extends "base.html" %}
   {% block title %}Page Title{% endblock %}
   {% block content %}
   <!-- Page content -->
   {% endblock %}
   ```

3. **Navigation** (`templates/base.html`):
   ```html
   <a href="/newpage" class="nav-link">New Page</a>
   ```

4. **Tests** (`tests/test_dashboard.py`):
   ```python
   def test_newpage(dashboard_client):
       resp = dashboard_client.get("/newpage")
       assert resp.status_code == 200
   ```

## Data Patterns

**Findings**: Load from `load_findings()` → returns `(findings, generated_at)` tuple.

**State DB**: Use `_state_db(conn_name)` context manager → yields `(BaseStateStore, connection_name)`.

**Aggregation**: Create functions in `data.py` that take findings/state data and return stats/grouped data.

**Charts**: Create Vega-Lite specs in `charts.py`, pass as JSON to templates via `json.dumps(spec)`.

## Common Pitfalls

- **Don't call `load_config()` in routes** - breaks tests. Use mocked helpers instead.
- **Don't connect to warehouse in routes** - dashboard should work offline. Read from state DB.
- **Always pass `connections` and `current_connection` to templates** - needed for connection selector.
- **Use `connection_name=""` for "all connections"** - state DB methods default to all when empty string.
- **Remember connection_name in findings** - filter by `f.connection_name or "default"` (empty string defaults to "default").

## Testing Requirements

- All new routes need tests
- All new data functions need unit tests
- Mock `_state_db()`, `_get_current_connection()`, `get_all_connections()` in fixtures
- Dashboard module coverage must be ≥80%
