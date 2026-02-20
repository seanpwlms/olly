"""Seed a toy DuckDB warehouse for manual testing.

Usage:
    uv run python dev/seed_db.py          # fresh environment + baseline snapshot
    uv run python dev/seed_db.py drift    # introduce schema/volume/freshness drift
    uv run python dev/seed_db.py verify   # setup, run checks, drift, run checks
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from olly.cli.check import run_checks
from olly.cli.snapshot import take_snapshot
from olly.config import (
    ConnectionConfig,
    ContractsConfig,
    DbtConfig,
    IntegrityConfig,
    NamedConnection,
    OllyConfig,
    Override,
    Selection,
    Settings,
    write_config,
)
from olly.models import DbtFinding, Finding
from olly.state import get_olly_dir

DEV_DIR = Path(__file__).resolve().parent
DB_PATH = DEV_DIR / "warehouse.duckdb"
SOURCE_DB_PATH = DEV_DIR / "source.duckdb"
TARGET_DB_PATH = DEV_DIR / "target.duckdb"
DATA_DIR = DEV_DIR / "data"
CONFIG_PATH = DEV_DIR / "olly.toml"
DBT_TARGET_DIR = DEV_DIR / "target"


def _seed_integrity_dbs() -> None:
    """Create source.duckdb and target.duckdb from CSVs for integrity checks."""
    for db_path in (SOURCE_DB_PATH, TARGET_DB_PATH):
        if db_path.exists():
            db_path.unlink()
        wal = db_path.with_suffix(".duckdb.wal")
        if wal.exists():
            wal.unlink()

    # Source: load both payments and shipments
    conn = duckdb.connect(str(SOURCE_DB_PATH))
    conn.execute(f"""
        CREATE TABLE payments AS
        SELECT * FROM read_csv_auto('{DATA_DIR}/source_payments.csv')
    """)
    conn.execute(f"""
        CREATE TABLE shipments AS
        SELECT * FROM read_csv_auto('{DATA_DIR}/source_shipments.csv')
    """)
    conn.close()

    # Target: load both payments and shipments (shipments has fewer rows)
    conn = duckdb.connect(str(TARGET_DB_PATH))
    conn.execute(f"""
        CREATE TABLE payments AS
        SELECT * FROM read_csv_auto('{DATA_DIR}/target_payments.csv')
    """)
    conn.execute(f"""
        CREATE TABLE shipments AS
        SELECT * FROM read_csv_auto('{DATA_DIR}/target_shipments.csv')
    """)
    conn.close()


def _write_dbt_run_results() -> None:
    """Write a sample dbt run_results.json with a mix of statuses."""
    DBT_TARGET_DIR.mkdir(exist_ok=True)
    invocation_id = str(uuid.uuid4())
    run_results = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/run-results/v5.json",
            "dbt_version": "1.7.0",
            "invocation_id": invocation_id,
        },
        "results": [
            {
                "unique_id": "model.shop.stg_orders",
                "status": "success",
                "execution_time": 1.23,
                "message": "OK created sql table model main.stg_orders",
            },
            {
                "unique_id": "model.shop.stg_payments",
                "status": "error",
                "execution_time": 0.45,
                "message": "Compilation Error in model stg_payments: column 'payment_method' does not exist",
            },
            {
                "unique_id": "model.shop.fct_orders",
                "status": "success",
                "execution_time": 142.3,
                "message": "OK created sql table model main.fct_orders",
            },
            {
                "unique_id": "test.shop.not_null_orders_id",
                "status": "pass",
                "execution_time": 0.12,
                "message": "Pass",
            },
            {
                "unique_id": "test.shop.not_null_payments_amount",
                "status": "fail",
                "execution_time": 0.38,
                "message": "Fail 3 (failure threshold: 0)",
            },
            {
                "unique_id": "test.shop.accepted_values_orders_status",
                "status": "warn",
                "execution_time": 0.21,
                "message": "Got 2 results, configured to warn if != 0",
            },
            {
                "unique_id": "snapshot.shop.snap_customers",
                "status": "success",
                "execution_time": 2.1,
                "message": "OK snapshotted",
            },
            {
                "unique_id": "model.shop.dim_customers",
                "status": "skipped",
                "execution_time": 0.0,
                "message": "SKIP relation shop.dim_customers",
            },
        ],
        "elapsed_time": 148.5,
    }
    out = DBT_TARGET_DIR / "run_results.json"
    out.write_text(json.dumps(run_results, indent=2))


def setup() -> OllyConfig:
    """Create a fresh warehouse, config, and baseline snapshot."""
    # Clean slate
    if DB_PATH.exists():
        DB_PATH.unlink()
    wal = DB_PATH.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()

    # Clean state directory for dev environment
    state_dir = get_olly_dir(DEV_DIR)
    if state_dir.exists():
        shutil.rmtree(state_dir)

    # Create warehouse
    conn = duckdb.connect(str(DB_PATH))

    conn.execute("""
        CREATE TABLE orders (
            id INTEGER,
            customer_id INTEGER,
            amount DOUBLE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE customers (
            id INTEGER,
            name VARCHAR,
            email VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE products (
            id INTEGER,
            name VARCHAR,
            price DOUBLE
        )
    """)

    # Seed orders — 100 rows with recent timestamps
    now = datetime.now()
    orders = [
        (
            i,
            (i % 10) + 1,
            round(10.0 + (i * 1.37 % 90), 2),
            now - timedelta(hours=i),
            now - timedelta(minutes=i * 5),
        )
        for i in range(1, 101)
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    # Seed customers — 10 rows
    customers = [(i, f"Customer {i}", f"customer{i}@example.com") for i in range(1, 11)]
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)

    # Seed products — 20 rows
    products = [(i, f"Product {i}", round(5.0 + i * 2.5, 2)) for i in range(1, 21)]
    conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)

    # View
    conn.execute("""
        CREATE VIEW order_summary AS
        SELECT
            customer_id,
            COUNT(*) AS order_count,
            SUM(amount) AS total_amount
        FROM orders
        GROUP BY customer_id
    """)

    conn.close()

    # Seed source/target databases for integrity checks
    _seed_integrity_dbs()

    # Write sample dbt run_results.json
    _write_dbt_run_results()

    # Write config
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path="warehouse.duckdb"),
        selection=Selection(include_schemas=["main"]),
        overrides=[Override(match="main.orders", freshness_column="updated_at")],
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(freshness_threshold_hours=24.0),
        sources={
            "source": "duckdb://source.duckdb",
            "target": "duckdb://target.duckdb",
        },
        dbt=DbtConfig(
            run_results_path="target/run_results.json",
            include_skipped=True,
        ),
        integrity=IntegrityConfig(module="integrity_pipelines.py"),
        contracts=ContractsConfig(module="contracts.py"),
    )
    write_config(config, CONFIG_PATH)

    # Take baseline snapshot (needs cwd in dev/ for StateDB)
    original_cwd = os.getcwd()
    os.chdir(DEV_DIR)
    try:
        results = take_snapshot(config)
    finally:
        os.chdir(original_cwd)

    print("Setup complete!")
    print(f"  Database: {DB_PATH}")
    print(f"  Config:   {CONFIG_PATH}")
    for name, snapshot_id, table_count, col_count in results:
        print(f"  Snapshot #{snapshot_id}: {table_count} tables, {col_count} columns")
    print()
    print("Verify baseline is clean:")
    print("  cd dev && uv run olly check")
    print()
    print("Then introduce drift:")
    print("  uv run python dev/seed_db.py drift")

    return config


def run_checks_in_dev(config: OllyConfig) -> tuple[list[Finding], list[DbtFinding]]:
    """Run checks with dev/ as cwd so StateDB uses the dev project state dir."""
    original_cwd = os.getcwd()
    os.chdir(DEV_DIR)
    try:
        findings, dbt_findings, _cost = run_checks(config)
        return findings, dbt_findings
    finally:
        os.chdir(original_cwd)


def take_snapshot_in_dev(
    config: OllyConfig,
) -> list[tuple[str, int, int, int]]:
    """Take a snapshot with dev/ as cwd so StateDB uses the dev project state dir."""
    original_cwd = os.getcwd()
    os.chdir(DEV_DIR)
    try:
        return take_snapshot(config)
    finally:
        os.chdir(original_cwd)


def add_volume_history(config: OllyConfig, snapshots: int | None = None) -> None:
    """Insert small batches and take snapshots to build volume history."""
    if snapshots is None:
        snapshots = max(config.settings.min_history_for_anomaly - 1, 0)
    next_order_id = 1000
    next_product_id = 2000

    for i in range(snapshots):
        conn = duckdb.connect(str(DB_PATH))
        now = datetime.now()

        orders = [
            (next_order_id + j, (j % 10) + 1, 42.0 + j, now, now) for j in range(1, 6)
        ]
        next_order_id += len(orders)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

        products = [
            (next_product_id + j, f"Extra Product {i}-{j}", 9.99 + j)
            for j in range(1, 4)
        ]
        next_product_id += len(products)
        conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)

        conn.close()

        results = take_snapshot_in_dev(config)
        for name, snapshot_id, table_count, col_count in results:
            print(
                f"History snapshot #{snapshot_id}: {table_count} tables, {col_count} columns"
            )


def assert_findings(
    findings: list[Finding],
    *,
    expect_any: bool,
    expect_types: set[str] | None = None,
) -> None:
    if expect_any and not findings:
        print("Error: expected findings but none were produced.", file=sys.stderr)
        sys.exit(1)
    if not expect_any and findings:
        print("Error: expected no findings but some were produced.", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding.check_type}: {finding.description}", file=sys.stderr)
        sys.exit(1)
    if expect_types:
        seen = {finding.check_type for finding in findings}
        missing = expect_types - seen
        if missing:
            print(
                f"Error: missing expected check types: {sorted(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)


def drift() -> None:
    """Introduce schema, volume, freshness, contract, and integrity drift."""
    if not CONFIG_PATH.exists():
        print("Error: no olly.toml found in dev/. Run setup first:", file=sys.stderr)
        print("  uv run python dev/seed_db.py", file=sys.stderr)
        sys.exit(1)

    conn = duckdb.connect(str(DB_PATH))

    # Schema drift: add column
    conn.execute("ALTER TABLE orders ADD COLUMN status VARCHAR")

    # Schema drift: drop column (also breaks Customers contract which expects email)
    conn.execute("ALTER TABLE customers DROP COLUMN email")

    # Schema drift: new table
    conn.execute("""
        CREATE TABLE returns (
            id INTEGER,
            order_id INTEGER,
            reason VARCHAR,
            created_at TIMESTAMP
        )
    """)
    conn.executemany(
        "INSERT INTO returns VALUES (?, ?, ?, ?)",
        [(i, i * 3, "defective", datetime.now()) for i in range(1, 6)],
    )

    # Volume drift: spike products from ~20 to ~10,020
    products = [
        (1000 + i, f"Bulk Product {i}", round(1.0 + i * 0.01, 2))
        for i in range(1, 10_001)
    ]
    conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)

    # Freshness drift: backdate orders.updated_at by 48 hours
    conn.execute("""
        UPDATE orders
        SET updated_at = updated_at - INTERVAL 48 HOURS
    """)

    # Contract drift: change products.price from DOUBLE to VARCHAR
    # (breaks Products contract which expects float)
    conn.execute("ALTER TABLE products ALTER COLUMN price TYPE VARCHAR")

    conn.close()

    # Integrity drift: delete rows from target shipments to create COUNT mismatch
    target_conn = duckdb.connect(str(TARGET_DB_PATH))
    target_conn.execute("DELETE FROM shipments WHERE id >= 4")
    target_conn.close()

    print("Drift introduced:")
    print(
        "  Schema:    orders.status added, customers.email dropped, new table 'returns'"
    )
    print("  Volume:    products spiked from ~20 to ~10,020 rows")
    print("  Freshness: orders.updated_at backdated by 48 hours")
    print("  Contracts: products.price changed to VARCHAR, customers.email dropped")
    print("  Integrity: target shipments rows deleted (COUNT mismatch)")
    print()
    print("Now run:")
    print("  cd dev && uv run olly check")


def verify() -> None:
    """Run setup, confirm clean baseline, then introduce drift and re-check."""
    config = setup()
    baseline_findings, _dbt = run_checks_in_dev(config)
    assert_findings(baseline_findings, expect_any=False)

    add_volume_history(config)

    drift()
    drift_findings, _dbt = run_checks_in_dev(config)
    assert_findings(
        drift_findings,
        expect_any=True,
        expect_types={"schema", "volume", "freshness", "contracts", "integrity"},
    )

    print("Verify complete: baseline clean, drift detected.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if mode == "setup":
        setup()
    elif mode == "drift":
        drift()
    elif mode == "verify":
        verify()
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        print(
            "Usage: uv run python dev/seed_db.py [setup|drift|verify]", file=sys.stderr
        )
        sys.exit(1)
