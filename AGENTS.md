# Olly

NEVER use git commands (git stash, git diff, git status, etc.) unless the user explicitly asks you to.

Data quality framework that monitors data warehouses for schema changes, volume anomalies, freshness issues, cross-source integrity, and contract violations. Supports DuckDB, Postgres, and BigQuery via Ibis.

## Commands

```
uv run olly init            # interactive setup wizard
uv run olly snapshot        # capture current warehouse state
uv run olly check           # detect changes (--json for machine output)
uv run olly config-explain  # show resolved config for each table
uv run olly serve           # start dashboard (requires [dashboard] extra)
uv run pytest tests/        # run tests
uv run ruff check           # lint
uv run ty check             # type check
uv run loq check            # file length check
```

## Architecture

CLI is a thin wrapper (`src/olly/__init__.py` → `src/olly/cli/`). All logic lives in importable Python modules so it is accessible via Python APIs:

- `config.py` — `olly.toml` parsing/writing (`load_config`, `write_config`), schema/table selection, override resolution, validation
- `adapter.py` — `Adapter` Protocol + `connect()` factory (dispatches on `ConnectionConfig.type`)
- `adapters/duckdb.py` — `DuckDBAdapter`: schema introspection, row counts, timestamps via Ibis
- `adapters/postgres.py` — `PostgresAdapter`: same interface for Postgres
- `adapters/bigquery.py` — `BigQueryAdapter`: same interface for BigQuery
- `state.py` — `StateDB` class wrapping SQLite (`~/.olly/<project-hash>/state.db`) for snapshot storage
- `checker.py` — core check orchestration (`run_checks`, `_run_dbt_checks`); imports all check modules and coordinates execution
- `models.py` — shared dataclasses (`TableInfo`, `VolumeRecord`, `Finding`, `Sync`, etc.) and enums (`IntegrityMethod`, `WindowOp`)
- `_import.py` — shared helpers for importing user-specified Python modules by file path or dotted name
- `contracts.py` — `TableContract` declarative API for schema assertions
- `explain.py` — config introspection / explanation output
- `results.py` — result formatting helpers
- `checks/schema.py` — schema diff detection (tables, columns, types, nullability)
- `checks/volume.py` — z-score based row count anomaly detection
- `checks/freshness.py` — timestamp freshness + row-count staleness proxy
- `checks/integrity.py` — cross-source data integrity syncs (`load_syncs`, `run_syncs`; methods: COUNT, HASH, PK, COUNT_DISTINCT)
- `checks/contracts.py` — validate warehouse schema against declared contracts
- `checks/dbt.py` — parse dbt `run_results.json` for failures
- `dashboard/` — FastAPI + Jinja2 web UI (`uv run olly serve`)

Key entry points for programmatic use: `cli/snapshot.py:take_snapshot()`, `checker.py:run_checks()`.

## Adapter Protocol

All warehouse interaction goes through the `Adapter` protocol (`adapter.py`). Use `connect(config)` to get an adapter instance, then call methods on it:

```python
from olly.adapter import connect
adapter = connect(config)
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

The `type` field in `[connection]` drives adapter selection. Adapter implementations live in `adapters/`.

## Ibis DuckDB API

Ibis uses `database=` not `schema=` for DuckDB:

```python
conn.list_tables(database="main")
conn.table("orders", database="main")
conn.list_databases()  # not list_schemas()
```

`raw_sql()` uses literal strings, not parameterized `?` placeholders.

## Config

`olly.toml` in project root. Connection is typed via `[connection]` with `type` + type-specific fields:

```toml
# DuckDB
[connection]
type = "duckdb"
path = "warehouse.duckdb"

# Postgres
[connection]
type = "postgres"
url = "postgresql://user:pass@host:5432/db"

# BigQuery
[connection]
type = "bigquery"
project = "my-project"
dataset = "analytics"                       # optional
use_information_schema_row_counts = true     # optional, default true

# Snowflake
[connection]
type = "snowflake"
account = "my-account"
database = "my_db"                          # optional
use_account_usage = false                   # optional, default false
user = "my-user"                            # optional, forwarded to ibis
role = "ANALYST"                            # optional, forwarded to ibis
warehouse = "COMPUTE_WH"                    # optional, forwarded to ibis
```

Any extra keys in `[connection]` beyond the known fields (`type`, `path`, `url`, `project`, `dataset`, `account`, `database`, `use_information_schema_row_counts`, `use_account_usage`) are forwarded as keyword arguments to the underlying Ibis `connect()` call.

Per-table overrides go under `[[overrides]]`. State lives in `~/.olly/<project-hash>/state.db` where the hash is based on the project root path.

Integrity syncs and contracts are defined in Python modules, referenced from TOML via the module-pointer pattern:

```toml
[integrity]
module = "integrity_syncs.py"   # file path or dotted module name

[contracts]
module = "contracts.py"
```

The Python module exports a module-level `syncs` list of `Sync` dataclasses (for integrity) or defines `TableContract` subclasses (for contracts). Both use `_import.py` to resolve the module.

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

- ✅ Tests: 116 passing (`uv run pytest tests/`)
- ✅ Lint: `uv run ruff check` clean
- ✅ Types: `uv run ty check` clean
- ✅ Loq: `uv run loq check` clean
- ✅ Coverage: 77% (`uv run pytest tests/ --cov=olly --cov-report=term-missing -q`)

If any tests fail, fix them before printing the results. Do not print the checklist with failures.

Code coverage must not fall below 80%. If your changes cause coverage to drop below this threshold, add tests to bring it back up before considering the task complete.
