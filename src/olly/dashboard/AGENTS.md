# Dashboard Development Guide

FastAPI JSON API + React SPA for Olly data quality monitoring. Dashboard displays findings, schema history, volume trends, dbt results, contracts, integrity syncs, usage/cost data, and disposition tracking.

## Architecture

```
app.py          → FastAPI app setup, SPA catch-all route, static file mounting
api_routes.py   → JSON API route handlers (all under /api prefix)
schemas.py      → Pydantic models: every dashboard-local shape, defined once
data.py         → Data aggregation functions (stats, filtering, grouping, timeseries); returns schemas.py models
data_checks.py  → Contracts and integrity page data builders
queries.py      → Raw state DB queries that return dicts/tuples (data.py calls these, then shapes results into models)
frontend/       → React + TypeScript SPA (Vite + TanStack Router)
  src/
    routes/     → Page components (file-based routing via TanStack Router)
    components/ → Reusable UI components
    hooks/
      queries.ts      → React Query hooks for all API endpoints
      useConnection.ts → Global connection selector (reads/writes URL search params)
      useTheme.ts      → Light/dark/system theme preference (persisted to localStorage)
    api.ts      → Generic fetch helpers (fetchApi, putApi)
    types.ts    → TypeScript type definitions mirroring Pydantic response models
static/dist/    → Built frontend assets (served by FastAPI)
```

## API Routes (`api_routes.py`)

All routes are prefixed with `/api`. JSON responses only.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/connections` | List all configured connections |
| GET | `/api/overview` | Dashboard home stats, trends, top tables |
| GET | `/api/findings` | Paginated findings with filters (check_type, severity, schema, disposition, q) |
| GET | `/api/tables` | Paginated table list with search/sort |
| GET | `/api/table/{schema}/{table}` | Table detail: schema, findings, volume timeseries, history, diff |
| GET | `/api/usage` | Usage stats, cost timeseries, least-used tables |
| GET | `/api/dbt` | dbt findings and stats |
| GET | `/api/contracts` | Contract validation results |
| GET | `/api/integrity` | Integrity sync results |
| PUT | `/api/findings/{finding_id}/disposition` | Set disposition (body: `{disposition, comment}`) |
| PUT | `/api/findings/bulk-disposition` | Bulk-set dispositions (body: `{finding_ids, disposition, comment}`) |
| GET | `/api/findings/{finding_id}/dispositions` | Disposition history for a finding |

## Frontend Routes

File-based routing via TanStack Router. Each file in `frontend/src/routes/` maps to a URL:

| File | URL | Description |
|------|-----|-------------|
| `index.tsx` | `/` | Overview dashboard |
| `findings.tsx` | `/findings` | Findings list with filters |
| `tables.tsx` | `/tables` | Tables list |
| `table.$schema.$table.tsx` | `/table/:schema/:table` | Table detail page |
| `usage.tsx` | `/usage` | Usage & cost analysis |
| `dbt.tsx` | `/dbt` | dbt results |
| `contracts.tsx` | `/contracts` | Contract validation results |
| `integrity.tsx` | `/integrity` | Integrity sync results |
| `__root.tsx` | — | Root layout with navigation |

## Key Principles

**No Warehouse Access**: Dashboard never connects to the warehouse directly. It reads from and writes to the state DB only. Disposition updates write back to state DB. The one exception is warehouse-backed state (`settings.state_schema`), where reaching the state store requires a warehouse adapter — `_state_db()` builds one only in that case and caches it in `_ADAPTER_CACHE` across requests. With the default SQLite state, no adapter is ever constructed.

**State-First**: All warehouse data comes from state DB (`~/.olly/state.db`), not live warehouse queries.

**Multi-Connection**: All API routes accept `connection` query parameter. Use `_get_current_connection()` helper to resolve connection name.

**SPA Architecture**: FastAPI serves the built React app. The catch-all route in `app.py` returns `index.html` for all non-API paths. Frontend uses React Query for data fetching and caching.

## Development Workflow

**Run Dashboard Locally**:
```bash
cd dev/
uv run python demo_dashboard.py  # Seeds demo data + launches dashboard
# Dashboard runs at http://localhost:8000
```

**Frontend Development**:
```bash
cd src/olly/dashboard/frontend/
npm install
npm run dev     # Vite dev server with HMR
npm run build   # Build to static/dist/
```

**Run Tests**:
```bash
uv run pytest tests/test_dashboard_api.py tests/test_dashboard_data.py tests/test_dashboard_checks.py -v
uv run pytest tests/test_dashboard_api.py tests/test_dashboard_data.py tests/test_dashboard_checks.py --cov=olly.dashboard --cov-report=term-missing
```

## Adding a New API Route

1. **Route** (`api_routes.py`):
   ```python
   @router.get("/newroute", response_model=NewRouteResponse)
   def api_newroute(connection: str = Query("")):
       conn_name = _get_current_connection(connection)
       with _state_db(conn_name) as (state_db, conn_name):
           # Load data from state DB
           data = ...
       return NewRouteResponse(data=DataModel.model_validate(data))
   ```
   Define the response model and any new shapes it needs in `schemas.py`, and have the `data.py` function build them directly.

2. **TypeScript types** (`frontend/src/types.ts`): Add response interfaces mirroring the Pydantic models.

3. **React Query hook** (`frontend/src/hooks/queries.ts`): Add a query hook using `fetchApi`/`putApi` from `api.ts`.

4. **Frontend route** (`frontend/src/routes/newroute.tsx`): Add page component.

5. **Tests** (`tests/test_dashboard_api.py`):
   ```python
   def test_newroute(dashboard_client):
       resp = dashboard_client.get("/api/newroute")
       assert resp.status_code == 200
   ```

## Data Patterns

**Findings from DB**: Use `load_findings_from_db(state_db)` to load from latest check run stored in state DB.

**Dispositions**: Call `hydrate_dispositions(findings, state_db)` to fill in disposition fields on findings.

**State DB**: Use `_state_db(conn_name)` context manager → yields `(BaseStateStore, connection_name)`.

**Aggregation**: Functions in `data.py` and `data_checks.py` take findings/state data and return Pydantic models from `schemas.py` directly — route handlers pass them straight into the response envelope. There is no intermediate dataclass layer.

**`model_validate()` is only for core dataclasses**: use it to convert the types `models.py` owns (`Finding`, `DbtFinding`, `TableInfo`) into their `*Model` mirrors. Never re-validate something that is already the right model.

## Common Pitfalls

- **Rebuild frontend after changes** — `olly serve` serves pre-built assets from `static/dist/`, not the Vite dev server. Run `npm run build` in `frontend/` after any frontend changes, then restart `olly serve`.
- **Don't connect to warehouse in routes** — dashboard should work offline. Read from state DB.
- **Use `connection_name=""` for "all connections"** — state DB methods default to all when empty string.
- **Remember connection_name in findings** — filter by `f.connection_name or "default"` (empty string defaults to "default").
- **Define shapes once, in `schemas.py`** — don't add a dataclass mirroring a Pydantic model. Add `ConfigDict(from_attributes=True)` only to models that get built from a `models.py` dataclass via `model_validate()`.
- **New endpoints go in `hooks/queries.ts`, not `api.ts`** — `api.ts` only has generic fetch helpers. Per-endpoint hooks belong in `queries.ts`.

## Testing Requirements

- All new API routes need tests in `tests/test_dashboard_api.py`
- All new data functions need unit tests in `tests/test_dashboard_data.py`
- Check-specific data builders (contracts, integrity) go in `tests/test_dashboard_checks.py`
- Mock `_state_db()`, `_get_current_connection()`, `_get_all_connections()` in fixtures
- Dashboard module coverage must be ≥80%
