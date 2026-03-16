from __future__ import annotations

from typing import Any

import duckdb
import pytest

from olly.adapters.duckdb import DuckDBAdapter
from olly.config import (
    ConnectionConfig,
    NamedConnection,
    OllyConfig,
    Override,
    Selection,
    Settings,
)
from olly.state import StateDB


@pytest.fixture(autouse=True)
def _isolate_olly_dir(tmp_path, monkeypatch):
    """Point get_olly_dir() at a temp directory so tests never touch ~/.olly/."""
    test_olly_dir = tmp_path / ".olly"
    monkeypatch.setattr("olly.state.sqlite.get_olly_dir", lambda: test_olly_dir)
    monkeypatch.setattr("olly.state.get_olly_dir", lambda: test_olly_dir)
    monkeypatch.setattr("olly.results.get_olly_dir", lambda: test_olly_dir)


@pytest.fixture
def duckdb_path(tmp_path):
    """Create a DuckDB database with test tables.

    Uses relative timestamps so tests don't become stale:
    - Orders created within last 2 days
    - Allows freshness tests to work with configurable thresholds
    """
    from datetime import datetime, timedelta

    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Use relative timestamps
    now = datetime.now()
    one_day_ago = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    conn.execute(
        "CREATE TABLE orders ("
        "  id INTEGER NOT NULL,"
        "  customer_id INTEGER NOT NULL,"
        "  amount DOUBLE NOT NULL,"
        "  created_at TIMESTAMP NOT NULL,"
        "  updated_at TIMESTAMP NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE customers ("
        "  id INTEGER NOT NULL,"
        "  name VARCHAR NOT NULL,"
        "  email VARCHAR"
        ")"
    )
    conn.execute(
        "CREATE VIEW order_summary AS "
        "SELECT customer_id, COUNT(*) as order_count, SUM(amount) as total "
        "FROM orders GROUP BY customer_id"
    )
    conn.execute(
        f"INSERT INTO orders VALUES "
        f"(1, 1, 99.99, '{now.strftime('%Y-%m-%d %H:%M:%S')}', '{now.strftime('%Y-%m-%d %H:%M:%S')}'),"
        f"(2, 2, 49.50, '{one_day_ago.strftime('%Y-%m-%d %H:%M:%S')}', '{one_day_ago.strftime('%Y-%m-%d %H:%M:%S')}'),"
        f"(3, 1, 25.00, '{two_days_ago.strftime('%Y-%m-%d %H:%M:%S')}', '{two_days_ago.strftime('%Y-%m-%d %H:%M:%S')}')"
    )
    conn.execute(
        "INSERT INTO customers VALUES "
        "(1, 'Alice', 'alice@example.com'),"
        "(2, 'Bob', 'bob@example.com')"
    )
    conn.close()
    return db_path


@pytest.fixture
def olly_config(duckdb_path):
    """Standard OllyConfig pointing at the test DuckDB."""
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path=str(duckdb_path)),
        selection=Selection(include_schemas=["main"]),
    )
    return OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )


@pytest.fixture
def olly_config_with_freshness(duckdb_path):
    """OllyConfig with a freshness_column override on orders."""
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path=str(duckdb_path)),
        selection=Selection(include_schemas=["main"]),
        overrides=[
            Override(
                match="main.orders",
                freshness_column="updated_at",
                freshness_threshold_hours=12,
            ),
        ],
    )
    return OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )


@pytest.fixture
def backend(duckdb_path):
    """DuckDBAdapter connected to the test DuckDB."""
    return DuckDBAdapter(str(duckdb_path))


@pytest.fixture
def state_db(tmp_path):
    """Initialized StateDB in a temp directory."""
    with StateDB(db_path=tmp_path / "state.db") as db:
        db.init_db()
        yield db


# --- Common test helpers ---


def make_table(name, columns, table_type="TABLE", schema="main"):
    """Build TableInfo for tests.

    Args:
        name: Table name
        columns: List of (column_name, type, nullable) tuples
        table_type: "TABLE" or "VIEW"
        schema: Schema name

    Example:
        make_table("orders", [("id", "int32", False), ("amount", "float64", False)])
    """
    from olly.models import ColumnInfo, TableInfo

    return TableInfo(
        schema_name=schema,
        table_name=name,
        table_type=table_type,
        columns=[ColumnInfo(*c) for c in columns],
    )


def make_finding(check_type="schema", severity="error", **kwargs):
    """Build Finding with sensible defaults for tests.

    Args:
        check_type: Type of check ("schema", "volume", "freshness", etc.)
        severity: "error" or "warning"
        **kwargs: Additional fields to override defaults

    Example:
        make_finding("volume", "warning", table_name="orders", details={"z_score": 3.5})
    """
    from olly.models import Finding

    defaults: dict[str, Any] = {
        "schema_name": "main",
        "table_name": "orders",
        "description": "Test finding",
        "connection_name": "primary",
    }
    defaults.update(kwargs)
    return Finding(check_type=check_type, severity=severity, **defaults)


def make_volume_record(schema="main", table="orders", count=100):
    """Build VolumeRecord with defaults.

    Example:
        make_volume_record("main", "users", 1000)
    """
    from olly.models import VolumeRecord

    return VolumeRecord(schema, table, count)


def make_cost_record(
    schema="main",
    table="orders",
    cost=10.0,
    user="user@example.com",
    bytes_billed=1_000_000,
    query_count=5,
):
    """Build CostRecord with defaults.

    Example:
        make_cost_record(schema="analytics", table="events", cost=25.5)
    """
    from olly.models import CostRecord

    return CostRecord(
        schema_name=schema,
        table_name=table,
        user_email=user,
        total_bytes_billed=bytes_billed,
        estimated_cost_usd=cost,
        query_count=query_count,
    )


def make_config(
    connection=None,
    selection=None,
    overrides=None,
    **kwargs,
):
    """Build OllyConfig with sensible defaults for tests.

    Args:
        connection: ConnectionConfig (defaults to DuckDB)
        selection: Selection (defaults to empty)
        overrides: List of Override objects
        **kwargs: Additional fields to override

    Example:
        make_config(connection=ConnectionConfig(type="postgres", url="..."))
    """
    from olly.config import ConnectionConfig, NamedConnection, OllyConfig, Selection, Settings

    if connection is None:
        connection = ConnectionConfig(type="duckdb", path="x.duckdb")
    if selection is None:
        selection = Selection()
    if overrides is None:
        overrides = []

    nc = NamedConnection(
        name="primary",
        connection=connection,
        selection=selection,
        overrides=overrides,
    )

    defaults: dict[str, Any] = {
        "connections": {"primary": nc},
        "settings": Settings(),
    }
    defaults.update(kwargs)
    return OllyConfig(**defaults)


class FakeAdapter:
    """Reusable mock adapter for testing contracts, cost checks, etc.

    Usage:
        # For contract tests:
        adapter = FakeAdapter(tables={
            ("main", "orders"): ibis.schema({"id": "int", "amount": "float"})
        })

        # For cost tests:
        adapter = FakeAdapter(cost_records=[make_cost_record(cost=25.0)])
    """

    def __init__(
        self,
        tables=None,
        cost_records=None,
        raise_on_fetch=False,
    ):
        self._tables = tables or {}
        self._cost_records = cost_records or []
        self._raise_on_fetch = raise_on_fetch

    def fetch_table_schema(self, schema_name, table_name):
        """Fetch schema for contracts tests."""
        if self._raise_on_fetch:
            raise RuntimeError("Test error")
        key = (schema_name, table_name)
        if key not in self._tables:
            raise RuntimeError(f"Table not found: {schema_name}.{table_name}")
        return self._tables[key]

    def fetch_query_costs(self, schemas, lookback_days, region, price_per_tb_usd):
        """Fetch costs for cost check tests."""
        if self._raise_on_fetch:
            raise RuntimeError("Test error")
        return self._cost_records


@pytest.fixture
def fake_adapter():
    """Fixture providing a FakeAdapter instance."""
    return FakeAdapter()


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    """TestClient with findings and state seeded in tmp_path.

    Seeds: 1 schema error + 1 volume warning on main.orders, plus a snapshot
    with schema and volume data.
    """
    from olly.models import ColumnInfo, Finding, TableInfo, VolumeRecord
    from olly.results import write_findings_json
    from helpers import patch_dashboard

    state_db_path = tmp_path / ".olly" / "state.db"
    state_db_path.parent.mkdir(parents=True)
    db = StateDB(db_path=state_db_path)
    db.init_db()

    snap_id = db.create_snapshot()
    db.store_schema_data(
        snap_id,
        [
            TableInfo(
                "main",
                "orders",
                "TABLE",
                [
                    ColumnInfo("id", "INTEGER", False),
                    ColumnInfo("amount", "DOUBLE", False),
                ],
            ),
        ],
    )
    db.store_volume_data(snap_id, [VolumeRecord("main", "orders", 100)])

    test_findings = [
        Finding("schema", "error", "main", "orders", "Column added: amount"),
        Finding("volume", "warning", "main", "orders", "Z-score 3.5"),
    ]
    db.store_findings(test_findings)
    db.close()

    findings_path = tmp_path / ".olly" / "findings.json"
    write_findings_json(test_findings, findings_path)

    return patch_dashboard(monkeypatch, state_db_path, tmp_path)
