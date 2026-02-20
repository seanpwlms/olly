# Olly

Data quality framework that monitors data warehouses for schema changes, volume anomalies, freshness issues, cross-source integrity, and contract violations. Supports DuckDB, Postgres, BigQuery, and Snowflake via [Ibis](https://ibis-project.org/).

🚨 This should be considered experimental and subject to change.

## Install

```bash
uv add olly
```

Install with an adapter:

```bash
uv add "olly[duckdb]"    # or postgres, bigquery
```

## Quickstart

```bash
olly init                 # interactive setup → creates olly.toml
olly snapshot             # capture current warehouse state
olly check                # detect changes since last snapshot
```

That's it. Olly compares consecutive snapshots and reports what changed.

## What it checks

| Check | What it detects | Severity |
|-------|----------------|----------|
| **Schema** | Added/removed tables, added/removed/changed columns, nullability changes | error or warning |
| **Volume** | Row count anomalies using z-score over snapshot history | warning |
| **Freshness** | Tables not updated within the configured threshold | warning |
| **Integrity** | Row count or hash mismatches between source and target databases | error |
| **Contracts** | Schema violations against declared Python contracts | error or warning |
| **dbt** | Failures from `run_results.json` | error or warning |
| **Usage** | Tables not queried within a lookback window (BigQuery only) | error or warning |
| **Cost** | Query cost spikes detected via z-score anomaly detection (BigQuery only) | warning |

## Example output

```text
Findings
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Check    ┃ Severity ┃ Table            ┃ Description                                                        ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ schema   │ error    │ main.customers   │ Column removed: main.customers.email                              │
│ schema   │ warning  │ main.orders      │ New column: main.orders.status                                    │
│ freshness│ warning  │ main.payments    │ Stale data: main.payments — last update 30.0h ago (threshold: 24.0h)│
│ volume   │ warning  │ main.orders      │ Row count anomaly (increase): main.orders (12,345 rows, z-score: +3.20) │
└──────────┴──────────┴──────────────────┴────────────────────────────────────────────────────────────────────┘

1 error(s), 3 warning(s)
```

Use `--json` for machine-readable output.

## CLI reference

```
olly init              Run the interactive setup wizard
olly snapshot          Capture current warehouse state
  --verbose            Print detailed progress
  --connection NAME    Only snapshot this connection
olly check             Run data quality checks
  --json               Machine-readable JSON output
  --verbose            Print detailed progress
  --write-results      Persist findings to ~/.olly/<project-hash>/findings.json (default: true)
  --no-write-results   Disable writing findings to disk
  --connection NAME    Only check this connection
olly config-explain    Show resolved config for each table
  --connection NAME    Only explain this connection
olly serve             Start the web dashboard
  --host HOST          Bind address (default: 127.0.0.1)
  --port PORT          Port (default: 8000)
```

## Configuration

Olly is configured via `olly.toml` in your project root. Run `olly init` to generate one interactively, or create it by hand.

### Connections

Each named connection under `[connections.<name>]` specifies a warehouse backend via `type` plus backend-specific fields. You can monitor multiple warehouses from a single config:

```toml
# DuckDB
[connections.primary]
type = "duckdb"
path = "warehouse.duckdb"          # omit for in-memory

# Postgres (second connection)
[connections.analytics]
type = "postgres"
url = "${DATABASE_URL}"

# BigQuery
[connections.warehouse]
type = "bigquery"
project = "my-project"
dataset = "analytics"                       # optional
use_information_schema_row_counts = true     # optional, default true

# Snowflake
[connections.snowflake]
type = "snowflake"
account = "my-account"
database = "my_db"                          # optional
use_account_usage = false                   # optional, default false
user = "my-user"                            # optional, forwarded to Ibis
role = "ANALYST"                            # optional, forwarded to Ibis
warehouse = "COMPUTE_WH"                    # optional, forwarded to Ibis
```

Any extra keys beyond the standard fields are forwarded as keyword arguments to the underlying Ibis `connect()` call. This lets you pass adapter-specific options (e.g. Snowflake `user`, `role`, `warehouse`, or DuckDB `read_only`) without Olly needing to know about them.

For BigQuery, set credentials via:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

### Selection

Each connection has its own selection. By default, all schemas are monitored (except `information_schema`) and all tables are included. Use glob patterns (`*`) to filter:

```toml
[connections.primary.selection]
include_schemas = ["*"]
exclude_schemas = ["information_schema", "scratch", "dev"]
include_tables = ["*.*"]
exclude_tables = ["main.tmp_*", "main.staging_*"]
```

### Settings

Global defaults for check thresholds:

```toml
[settings]
freshness_threshold_hours = 24.0    # max age before flagging stale
volume_zscore_threshold = 3.0       # z-score cutoff for volume anomalies
history_depth = 30                  # snapshots to keep for trend analysis
min_history_for_anomaly = 5         # minimum snapshots before volume checks run
write_results = true                # persist findings to ~/.olly/<project-hash>/findings.json
```

### Overrides

Override settings for specific tables or patterns, scoped per connection. Later overrides take precedence:

```toml
[[connections.primary.overrides]]
match = "main.orders"
freshness_threshold_hours = 168
volume_zscore_threshold = 5.0

[[connections.primary.overrides]]
match = "main.*"
freshness_column = "updated_at"
```

Use `olly config-explain` to see how overrides resolve for each table.

### Cross-source integrity

Compare data between two databases. Define named sources in TOML and syncs in Python:

```toml
[sources]
warehouse = "duckdb:///warehouse.duckdb"
replica = "postgresql://${PGUSER}:${PGPASSWORD}@replica:5432/db"

[integrity]
module = "integrity_syncs.py"   # file path or dotted module name
```

```python
# integrity_syncs.py
from olly.models import IntegrityMethod, Sync, WindowOp, WindowSpec

syncs = [
    Sync(
        name="orders_count",
        source="warehouse",
        target="replica",
        source_table="main.orders",
        target_table="public.orders",
        method=IntegrityMethod.COUNT,
        watermark="updated_at",
        window=WindowSpec(op=WindowOp.GT_NOW, duration="2h"),
    ),
]
```

Methods:

| Method | What it compares |
|--------|-----------------|
| `count` | Row counts between source and target |
| `count_distinct` | Distinct values of a key column |
| `pk` | Primary key sets (finds missing/extra rows) |
| `hash` | Row-level hash of specified columns |

Pipelines support time windows, WHERE filters, tolerance thresholds, and watermark columns for incremental checks.

### Contracts

Define expected table schemas as Python classes:

```python
# contracts.py
from datetime import datetime
from olly.contracts import TableContract

class Orders(TableContract):
    __table__ = "orders"
    __schema__ = "main"
    __connection__ = "primary"  # only check against this connection (optional)
    __strict__ = True           # flag unexpected columns

    id: int
    amount: float
    created_at: datetime
    customer_name: str | None   # nullable
```

When `__connection__` is set, the contract is only validated against that named connection. When omitted, it runs against all connections.

Point your config at the contracts module:

```toml
[contracts]
module = "contracts.py"     # file path or dotted module name
```

Olly validates the warehouse schema against your contracts on every `olly check`.

### dbt integration

Parse dbt's `run_results.json` to surface failures:

```toml
[dbt]
run_results_path = "target/run_results.json"
```

### Table usage monitoring

Detect tables that haven't been queried recently. Currently supported on BigQuery only (uses `INFORMATION_SCHEMA.JOBS_BY_PROJECT`).

```toml
[usage]
enabled = true
lookback_days = 90          # how far back to scan query history
unused_threshold_days = 30  # days without queries before flagging
bigquery_region = "us"
```

Tables with no queries in the lookback window are flagged as errors. Tables queried but not within the unused threshold are warnings.

### Query cost monitoring

Track BigQuery query costs and detect spending spikes. Uses z-score anomaly detection over cost history from previous snapshots.

```toml
[cost]
enabled = true
lookback_days = 30          # days of query history to aggregate
bigquery_region = "us"
price_per_tb_usd = 6.25     # on-demand pricing rate
spike_threshold = 3.0        # z-score threshold for cost spike alerts
```

When `olly check` runs, it shows a cost summary with top tables and top users by spend. Cost spikes are flagged as findings when the current period's total exceeds the historical mean by more than `spike_threshold` standard deviations.

## Python API

All functionality is available as importable Python modules:

```python
from olly.cli.check import run_checks
from olly.cli.snapshot import take_snapshot
from olly.config import (
    ConnectionConfig, NamedConnection, OllyConfig, Selection, Settings,
)

nc = NamedConnection(
    name="primary",
    connection=ConnectionConfig(type="duckdb", path="warehouse.duckdb"),
    selection=Selection(include_schemas=["main"]),
)
config = OllyConfig(
    connections={"primary": nc},
    settings=Settings(),
)

take_snapshot(config)
findings, dbt_findings, cost_records = run_checks(config)

for finding in findings:
    print(f"[{finding.connection_name}] {finding.check_type}: {finding.description}")
```

## Web dashboard

Install the dashboard extra and start the server:

```bash
uv add "olly[dashboard]"
olly serve
```

The dashboard reads from `~/.olly/<project-hash>/findings.json` (written by `olly check`) and displays findings in a web UI at `http://127.0.0.1:8000`.

## How it works

Olly uses a snapshot-and-diff model:

1. **`olly snapshot`** connects to your warehouse via Ibis, introspects schemas and tables, and stores schema info and row counts in a local SQLite database (`~/.olly/<project-hash>/state.db`).

2. **`olly check`** takes a new snapshot and compares it to the previous one. It runs schema diffs, volume anomaly detection (z-score over history), freshness checks, and any configured integrity/contract/dbt checks.

3. Findings are printed to the terminal and optionally written to `~/.olly/<project-hash>/findings.json` for the dashboard or downstream tooling.

State is fully local — Olly only reads from your warehouse and writes to the `~/.olly/<project-hash>/` directory.

## Development

```bash
uv sync --group dev
uv run pytest tests/
uv run ruff check
uv run ty check
```
