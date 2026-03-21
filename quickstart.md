# Quickstart

This walks through setting up Olly against a DuckDB instance. The same steps apply to Postgres, BigQuery, and Snowflake — only the connection config differs.

## 1. Install

```bash
pip install "olly-core[duckdb,dashboard]"
```
or
```bash
uv add "olly-core[duckdb,dashboard]"
```

<!-- Replace `duckdb` with your adapter: `postgres`, `bigquery`, or `snowflake`. -->

## 2. Create a sample database

Create a DuckDB file with some tables to monitor:

```python
import duckdb

conn = duckdb.connect("warehouse.duckdb")
conn.execute("CREATE TABLE orders (id INT, customer_id INT, amount DOUBLE, created_at TIMESTAMP)")
conn.execute("CREATE TABLE customers (id INT, name VARCHAR, email VARCHAR)")
conn.execute("INSERT INTO orders VALUES (1, 1, 99.99, '2024-01-15 10:00:00'), (2, 2, 49.50, '2024-01-16 11:00:00')")
conn.execute("INSERT INTO customers VALUES (1, 'Alice', 'alice@example.com'), (2, 'Bob', 'bob@example.com')")
conn.close()
```

## 3. Create config

Run the interactive wizard:

```bash
olly init
```
Specify duckdb, and choose `warehouse.duckdb` as the location.
This creates an `olly.toml` in your project root and initializes the state database. If you do not have a duckdb database, at the path you specified, one will be created.

The generated config looks like:
```toml
[connections.primary]
type = "duckdb"
path = "warehouse.duckdb"

[connections.primary.selection]
include_schemas = ["*"]
exclude_schemas = ["information_schema"]
```

You can also create `olly.toml` by hand. See the [README](README.md#configuration) for all connection types.

## 4. Verify connectivity

```bash
olly debug
```

This connects to your warehouse and lists available schemas.

## 5. Take your first snapshot

```bash
olly snapshot
```

Olly connects to your warehouse, reads schema metadata and row counts, and stores them locally in `~/.olly/state.db`. This is your baseline.

## 6. Make a change

Simulate what happens when a pipeline or migration alters your warehouse:

```python
import duckdb

conn = duckdb.connect("warehouse.duckdb")
conn.execute("ALTER TABLE orders ADD COLUMN status VARCHAR")
conn.execute("INSERT INTO orders VALUES (3, 1, 75.00, '2024-01-17 09:00:00', 'shipped')")
conn.close()
```

## 7. Take a second snapshot

```bash
olly snapshot
```

## 8. Run checks

```bash
olly check
```

Olly compares the two snapshots and reports any schema changes, volume anomalies, or freshness issues. If everything is clean you'll see:

Use `--json` for machine-readable output, or `--select` to run specific check types:
```bash
olly check --json
olly check --select schema,volume
```

## 9. Filter what you monitor

By default, Olly monitors all schemas and objects. Narrow the scope with selection filters:

```toml
[connections.primary.selection]
include_schemas = ["main"]
exclude_tables = ["main.tmp_*", "main.staging_*"]
```

## 10. Configure per-table settings

Use overrides to set freshness columns and adjust thresholds for specific tables:

```toml
[[connections.primary.overrides]]
match = "main.*"
freshness_threshold_hours = 24

[[connections.primary.overrides]]
match = "main.orders"
freshness_threshold_hours = 12
```

More specific matches take precedence. Run `olly plan` to see how overrides resolve for each table.

## 11. View the dashboard

```bash
olly serve
```

This starts a web UI at `http://127.0.0.1:8000` that displays findings from previous check runs.

## What's next

- **[Contracts](README.md#contracts)** — declare expected schemas as Python classes
- **[Integrity checks](README.md#cross-connection-integrity)** — compare data across connections
- **[dbt integration](README.md#dbt-integration)** — surface failures from `run_results.json`
- **[Usage & cost](README.md#table-usage-monitoring)** — detect unused tables and cost spikes (BigQuery)
