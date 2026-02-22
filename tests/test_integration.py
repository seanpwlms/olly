"""End-to-end integration tests for the olly workflow."""

import duckdb

from olly.adapter import connect_typed
from olly.checker import run_checks
from olly.checks.schema import check_schema
from olly.cli.snapshot import take_snapshot
from olly.config import (
    ConnectionConfig,
    NamedConnection,
    OllyConfig,
    Selection,
    Settings,
    write_config,
)
from olly.state import StateDB


def test_full_workflow(tmp_path):
    """init -> snapshot -> alter schema -> snapshot -> check detects changes."""
    db_path = tmp_path / "warehouse.duckdb"
    state_path = tmp_path / "state.db"

    # Set up warehouse
    raw = duckdb.connect(str(db_path))
    raw.execute("CREATE TABLE orders (id INT NOT NULL, amount DOUBLE NOT NULL)")
    raw.execute("CREATE TABLE customers (id INT NOT NULL, name VARCHAR, email VARCHAR)")
    raw.execute("INSERT INTO orders VALUES (1, 10.0), (2, 20.0)")
    raw.execute("INSERT INTO customers VALUES (1, 'Alice', 'a@b.com')")
    raw.close()

    conn = ConnectionConfig(type="duckdb", path=str(db_path))
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )

    # Take baseline snapshot
    backend = connect_typed(config.connections["primary"].connection)
    tables = backend.fetch_schema_info(["main"])
    volumes = backend.fetch_row_counts(tables)

    state_db = StateDB(db_path=state_path)
    state_db.init_db()
    sid = state_db.create_snapshot()
    state_db.store_schema_data(sid, tables)
    state_db.store_volume_data(sid, volumes)

    # Alter the warehouse
    raw = duckdb.connect(str(db_path))
    raw.execute("ALTER TABLE orders ADD COLUMN status VARCHAR")
    raw.execute("ALTER TABLE customers DROP COLUMN email")
    raw.execute("CREATE TABLE products (id INT NOT NULL, price DOUBLE)")
    raw.close()

    # Take second snapshot with the changes
    backend2 = connect_typed(config.connections["primary"].connection)
    current_tables = backend2.fetch_schema_info(["main"])
    current_volumes = backend2.fetch_row_counts(current_tables)
    sid2 = state_db.create_snapshot()
    state_db.store_schema_data(sid2, current_tables)
    state_db.store_volume_data(sid2, current_volumes)

    # Run schema checks comparing the two snapshots
    latest_tables = state_db.get_latest_schema()
    baseline_tables = state_db.get_second_latest_schema()
    findings = check_schema(latest_tables, baseline_tables)
    state_db.close()

    changes = {f.details["change"] for f in findings}
    assert "table_added" in changes  # products
    assert "column_added" in changes  # orders.status
    assert "column_removed" in changes  # customers.email

    # Check specific tables
    added_table = next(f for f in findings if f.details["change"] == "table_added")
    assert added_table.table_name == "products"

    removed_col = next(f for f in findings if f.details["change"] == "column_removed")
    assert removed_col.table_name == "customers"
    assert removed_col.details["column"] == "email"


def test_snapshot_and_check_via_api(tmp_path, monkeypatch):
    """Test using the higher-level take_snapshot / run_checks API."""
    db_path = tmp_path / "warehouse.duckdb"
    config_path = tmp_path / "olly.toml"

    # Set up warehouse
    raw = duckdb.connect(str(db_path))
    raw.execute("CREATE TABLE t (id INT NOT NULL, val VARCHAR)")
    raw.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    raw.close()

    conn = ConnectionConfig(type="duckdb", path=str(db_path))
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )
    write_config(config, config_path)

    # Monkeypatch so modules find config and state in tmp_path
    monkeypatch.chdir(tmp_path)

    # Take first snapshot
    results = take_snapshot(config)
    _, snapshot_id, table_count, col_count = results[0]
    assert snapshot_id == 1
    assert table_count == 1
    assert col_count == 2

    # Take second snapshot with no changes -> clean check
    results = take_snapshot(config)
    _, snapshot_id, _, _ = results[0]
    assert snapshot_id == 2
    findings, _dbt, _cost = run_checks(config)
    assert findings == []

    # Alter and take another snapshot
    raw = duckdb.connect(str(db_path))
    raw.execute("ALTER TABLE t ADD COLUMN new_col INT")
    raw.close()

    # Take third snapshot to capture the change
    take_snapshot(config)

    # Check detects the change between snapshots 2 and 3
    findings, _dbt, _cost = run_checks(config)
    assert len(findings) >= 1
    assert any(f.details.get("change") == "column_added" for f in findings)


def test_volume_anomaly_detection_e2e(tmp_path, monkeypatch):
    """Build volume history, then spike row count and detect anomaly."""
    db_path = tmp_path / "warehouse.duckdb"

    raw = duckdb.connect(str(db_path))
    raw.execute("CREATE TABLE t (id INT NOT NULL)")
    raw.close()

    conn = ConnectionConfig(type="duckdb", path=str(db_path))
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(min_history_for_anomaly=5),
    )

    monkeypatch.chdir(tmp_path)

    # Build history with ~100 rows
    for i in range(6):
        raw = duckdb.connect(str(db_path))
        raw.execute("DELETE FROM t")
        for j in range(100 + i):
            raw.execute(f"INSERT INTO t VALUES ({j})")
        raw.close()
        take_snapshot(config)

    # Spike to 10000 rows and take snapshot
    raw = duckdb.connect(str(db_path))
    raw.execute("DELETE FROM t")
    for j in range(10000):
        raw.execute(f"INSERT INTO t VALUES ({j})")
    raw.close()
    take_snapshot(config)

    findings, _dbt, _cost = run_checks(config)
    volume_findings = [f for f in findings if f.check_type == "volume"]
    assert len(volume_findings) == 1
    assert volume_findings[0].details["z_score"] > 3.0


def test_exit_codes(tmp_path, monkeypatch):
    """Check that run_checks returns empty list when clean."""
    db_path = tmp_path / "warehouse.duckdb"

    raw = duckdb.connect(str(db_path))
    raw.execute("CREATE TABLE t (id INT NOT NULL)")
    raw.execute("INSERT INTO t VALUES (1)")
    raw.close()

    conn = ConnectionConfig(type="duckdb", path=str(db_path))
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )

    monkeypatch.chdir(tmp_path)

    # Take 2 snapshots with no changes between them
    take_snapshot(config)
    take_snapshot(config)
    findings, _dbt, _cost = run_checks(config)
    assert findings == []  # exit code 0 case
