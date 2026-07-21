# Olly

NEVER use git commands (git stash, git diff, git status, etc.) unless the user explicitly asks you to.

Data quality framework that monitors data warehouses for schema changes, volume anomalies, freshness issues, cross-source integrity, cost spikes, usage staleness, and contract violations. Supports DuckDB, Postgres, BigQuery, and Snowflake via Ibis.

## Commands

```
uv run olly init            # interactive setup wizard
uv run olly snapshot        # capture current warehouse state
uv run olly check           # detect changes (--json for machine output)
uv run olly plan            # show resolved config for each table
uv run olly unused          # show unused/stale tables
uv run olly debug           # test warehouse connectivity
uv run olly clean           # delete local state database
uv run olly serve           # start dashboard (requires [dashboard] extra)
uv run pytest tests/        # run tests
uv run ruff check           # lint
uv run ty check             # type check
uv run loq check            # file length check
```

Most CLI commands accept `--connection <name>` to target a specific named connection (defaults to all).

## Architecture

CLI is a thin wrapper (`src/olly/__init__.py` → `src/olly/cli/`). All logic lives in importable Python modules so it is accessible via Python APIs:

- `config.py` — `olly.toml` parsing/writing (`load_config`, `write_config`); defines all config dataclasses (`OllyConfig`, `ConnectionConfig`, `Selection`, `Override`, `Settings`, `NamedConnection`, etc.)
- `config_ops.py` — config resolution helpers: `select_schema_names`, `filter_table_infos`, `resolve_table_settings_with_sources`, `resolve_connections`, `validate_config`, `match_pattern`
- `adapter.py` — `Adapter` Protocol + `connect_typed()` factory (dispatches on `ConnectionConfig.type`)
- `adapters/base.py` — `BaseAdapter`: shared implementation for all adapters (schema introspection, row counts, timestamps, hashing)
- `adapters/duckdb.py` — `DuckDBAdapter`: DuckDB-specific overrides via Ibis
- `adapters/postgres.py` — `PostgresAdapter`: Postgres-specific overrides
- `adapters/bigquery.py` — `BigQueryAdapter`: BigQuery-specific overrides (information_schema row counts, usage/cost queries)
- `adapters/snowflake.py` — `SnowflakeAdapter`: Snowflake-specific overrides (account_usage, dotted `database.schema` notation)
- `state/` — state storage package:
  - `base.py` — `BaseStateStore` ABC with all shared business logic (snapshots, findings, dispositions, cost records); `open_state()` factory
  - `sqlite.py` — `StateDB(BaseStateStore)`: SQLite-backed store (`~/.olly/state.db`)
  - `warehouse.py` — `WarehouseStateStore(BaseStateStore)`: stores state in warehouse tables (enabled via `settings.state_schema`)
- `checker.py` — core check orchestration (`run_checks`); coordinates all check modules per connection, then runs global checks (integrity, dbt)
- `models.py` — shared dataclasses (`TableInfo`, `ColumnInfo`, `VolumeRecord`, `UsageRecord`, `CostRecord`, `Finding`, `Sync`, `DbtFinding`, `WindowSpec`) and enums (`IntegrityMethod`, `WindowOp`, `VolumeMethod`, `Disposition`)
- `_import.py` — shared helpers for importing user-specified Python modules by file path or dotted name
- `contracts.py` — `TableContract` declarative API for schema assertions
- `plan.py` — config introspection / plan resolution (`resolve_plan`, `format_plan`)
- `results.py` — result formatting helpers
- `slack.py` — Slack alerting (`build_slack_payload`, `send_slack_alert`); posts findings to a webhook URL
- `logging.py` — `setup_logging(verbose)`: configures the `"olly"` logger hierarchy
- `checks/schema.py` — schema diff detection (tables, columns, types, nullability)
- `checks/volume.py` — row count anomaly detection via EWMA (default) or z-score
- `checks/freshness.py` — timestamp freshness + row-count staleness proxy
- `checks/integrity.py` — cross-source data integrity syncs (`load_syncs`, `run_syncs`; methods: COUNT, HASH, PK, COUNT_DISTINCT)
- `checks/contracts.py` — validate warehouse schema against declared contracts
- `checks/usage.py` — table usage/staleness detection (unused tables, stale tables based on last query time)
- `checks/cost.py` — cost monitoring; detects cost spikes via z-score against historical average
- `checks/dbt.py` — parse dbt `run_results.json` for failures
- `dashboard/` — FastAPI JSON API + React SPA (`uv run olly serve`). See `src/olly/dashboard/AGENTS.md` for detailed dashboard development guide.

Key entry points for programmatic use: `cli/snapshot.py:take_snapshot()`, `checker.py:run_checks()`.

## Check execution order

`run_checks()` runs the following per connection:

1. **Usage** (`check_usage`) — if `config.usage.enabled`; independent of snapshots
2. **Cost** (`check_cost`) — if `config.cost.enabled`; stores cost records to state
3. Requires at least 2 snapshots for the remaining checks:
4. **Schema** (`check_schema`) — compares latest vs. second-latest schema snapshots
5. **Contracts** (`check_contracts`) — if `config.contracts.module` set
6. **Volume** (`check_volume`) — per-table thresholds resolved via `resolve_table_settings_with_sources`
7. **Freshness** (`check_freshness`) — per-table thresholds resolved the same way

After all connections:

8. **Integrity** (`run_syncs`) — global, not per-connection; if `config.integrity.module` set
9. **dbt** (`check_dbt`) — global; if `config.dbt.run_results_path` set

## Adapter Protocol

All warehouse interaction goes through the `Adapter` protocol (`adapter.py`). Typical usage from config to adapter:

```python
from olly.config import load_config
from olly.config_ops import resolve_connections
from olly.adapter import connect_typed

config = load_config()
for name, nc in resolve_connections(config, connection_name=None):
    adapter = connect_typed(nc.connection)
    adapter.list_schemas()
    adapter.fetch_schema_info(schemas)
    adapter.fetch_row_counts(table_infos)
    adapter.fetch_max_timestamp(schema, table, column)
    adapter.fetch_count(schema, table, where_sql)
    adapter.fetch_count_distinct(schema, table, column, where_sql)
    adapter.fetch_table_schema(schema, table)
    adapter.fetch_table_usage(schemas, lookback_days, region)
    adapter.fetch_query_costs(schemas, lookback_days, region, price_per_tb_usd)
    adapter.fetch_hash(schema, table, columns, order_by, where_sql)
```

The `type` field in `[connection]` drives adapter selection: `duckdb`, `postgres`, `bigquery`, `snowflake`. Adapter implementations live in `adapters/`, all extending `BaseAdapter`.

## Findings & Dispositions

**`Finding`** — the primary output of all checks:

- `check_type: str` — `"schema"`, `"volume"`, `"freshness"`, `"usage"`, `"cost"`, `"integrity"`, `"contract"`, `"dbt"`
- `severity: str` — `"warning"` or `"error"`
- `schema_name: str`, `table_name: str`, `description: str`
- `details: dict` — check-specific metadata
- `connection_name: str` — which named connection produced this finding
- `disposition: str` — workflow status (`"not_started"`, `"no_action"`, `"in_progress"`, `"completed"`)
- `id: int | None`, `created_at: str`

**`Disposition`** enum: `NOT_STARTED`, `NO_ACTION`, `IN_PROGRESS`, `COMPLETED`. Set via the dashboard UI or `state.set_disposition()`. Dispositions are tracked in a separate history table, so each status change is an auditable event.

## Ibis adapter gotchas

**DuckDB**: Ibis uses `database=` not `schema=` for DuckDB:

```python
conn.list_tables(database="main")
conn.table("orders", database="main")
conn.list_databases()  # not list_schemas()
```

**Snowflake**: Schema names use dotted `"database.schema"` notation throughout the adapter. The internal `_split_schema()` helper parses this. Table references are three-part: `"database"."schema"."table"`.

**All adapters**: `raw_sql()` uses literal strings, not parameterized `?` placeholders.

## Config

`olly.toml` in project root. Two formats are supported:

### Single connection

```toml
[connection]
type = "duckdb"
path = "warehouse.duckdb"

[selection]
include_schemas = ["*"]
exclude_schemas = ["information_schema"]

[[overrides]]
match = "analytics.*"
freshness_column = "updated_at"
```

### Multi-connection

```toml
[connections.primary]
type = "duckdb"
path = "warehouse.duckdb"

[connections.primary.selection]
include_schemas = ["main"]

[[connections.primary.overrides]]
match = "main.orders"
freshness_column = "updated_at"

[connections.replica]
type = "postgres"
url = "postgresql://user:pass@host:5432/db"
```

### Connection types

```toml
# DuckDB
type = "duckdb"
path = "warehouse.duckdb"

# Postgres
type = "postgres"
url = "postgresql://user:pass@host:5432/db"

# BigQuery
type = "bigquery"
project = "my-project"
dataset = "analytics"                       # optional
region = "us"                               # optional
use_information_schema_row_counts = true     # optional, default true

# Snowflake
type = "snowflake"
account = "my-account"
database = "my_db"                          # optional
use_account_usage = false                   # optional, default false
user = "my-user"                            # optional, forwarded to ibis
role = "ANALYST"                            # optional, forwarded to ibis
warehouse = "COMPUTE_WH"                    # optional, forwarded to ibis
```

Any extra keys beyond the known fields are forwarded as keyword arguments to the underlying Ibis `connect()` call.

### Overrides

Per-table setting overrides via `[[overrides]]`. More specific matches win. Precedence from lowest to highest:

| `match` pattern | Specificity | Example |
|---|---|---|
| `schema` | Lowest — applies to all tables in schema | `analytics` |
| `schema.*` | Middle — wildcard pattern match | `analytics.order_*` |
| `schema.table` | Highest — exact table match | `analytics.orders` |

Override fields:
- `freshness_column` — column name for freshness checks
- `freshness_threshold_hours` — max age before alerting (default: 24.0)
- `volume_zscore_threshold` — z-score threshold for volume anomalies (default: 3.0)
- `volume_method` — `"ewma"` (default) or `"zscore"`

### Other config sections

- `[settings]` — global defaults: `history_depth`, `volume_zscore_threshold`, `volume_method`, `freshness_threshold_hours`, `min_history_for_anomaly`, `write_results`, `state_schema`
- `[integrity]` — `module` pointing to a Python file exporting a `syncs` list of `Sync` dataclasses
- `[contracts]` — `module` pointing to a Python file defining `TableContract` subclasses
- `[dbt]` — `run_results_path`, `include_skipped`
- `[usage]` — `enabled`, `lookback_days`, `unused_threshold_days`, `bigquery_region`, `rollup_schemas` (collapse fully-inactive schemas into one finding, default true), `schema_unused_threshold_pct` (also flag schemas with ≥ this % inactive tables, default 100)
- `[cost]` — `enabled`, `lookback_days`, `bigquery_region`, `price_per_tb_usd`, `spike_threshold`
- `[slack]` — `webhook_url`, `on_error`, `on_warning`

See `config.py` for authoritative field names, types, and defaults. Both `[integrity]` and `[contracts]` use `_import.py` to resolve the module reference.

## Extending the codebase

**Adding a new check type**:
1. Create `checks/foo.py` with a function returning `list[Finding]`
2. If the check needs new record types, add dataclasses to `models.py`
3. Wire it into `checker.py:run_checks()` (per-connection or global, depending on scope)
4. Add config dataclass to `config.py` and parse it in `load_config()`
5. If findings should appear in the dashboard, add API/frontend support (see `src/olly/dashboard/AGENTS.md`)
6. Add tests

**Adding a new adapter**:
1. Subclass `BaseAdapter` in `adapters/foo.py`
2. Override methods where the default SQL doesn't work for your warehouse
3. Register the type string in `adapter.py:connect_typed()`
4. Add connection fields to `ConnectionConfig` in `config.py`
5. Add tests

**Adding a CLI command**:
1. Create `cli/foo.py` with a `run_foo()` function
2. Register with `@app.command` in `__init__.py`

## Dev environment

`dev/` contains a self-contained demo environment for manual testing:

```
uv run python dev/seed_db.py            # create warehouse, config, baseline snapshot
uv run python dev/seed_db.py drift      # introduce schema/volume/freshness/contract/integrity drift
uv run python dev/seed_db.py verify     # end-to-end: setup → baseline check → history → drift → re-check
uv run python dev/demo_dashboard.py     # seed + launch dashboard
uv run python dev/clean_demo.py         # remove all generated files
```

- `seed_db.py` — creates a DuckDB warehouse (`warehouse.duckdb`), source/target DBs for integrity checks, sample dbt `run_results.json`, and an `olly.toml`. The `verify` mode is the full smoke test: asserts baseline is clean, then asserts drift is detected across all check types.
- `demo_dashboard.py` — runs the full seed + drift cycle and starts `olly serve` for visual testing.
- `contracts.py` — sample `TableContract` subclasses for the dev warehouse. DuckDB columns default to nullable, so all columns use `T | None`.
- `integrity_pipelines.py` — sample `Sync` definitions for cross-source integrity checks in the dev environment.
- `clean_demo.py` — removes the state directory, `*.duckdb`, and WAL files from `dev/`.

## Tests

All tests use `tmp_path` / `monkeypatch` for isolation — no shared state. Fixtures in `tests/conftest.py` create a DuckDB with `orders`, `customers`, and `order_summary` view.

After any implementation change, run all checks and report results in this format:

- ✅ Tests: passing (`uv run pytest tests/`)
- ✅ Lint: `uv run ruff check` clean
- ✅ Types: `uv run ty check` clean
- ✅ Loq: `uv run loq check` clean
- ✅ Coverage: above 80% (`uv run pytest tests/ --cov=olly --cov-report=term-missing -q`)

If any tests fail, fix them before printing the results. Do not print the checklist with failures.

Code coverage must not fall below 80%. If your changes cause coverage to drop below this threshold, add tests to bring it back up before considering the task complete.
