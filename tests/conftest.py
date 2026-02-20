from __future__ import annotations

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


@pytest.fixture
def duckdb_path(tmp_path):
    """Create a DuckDB database with test tables."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
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
        "INSERT INTO orders VALUES "
        "(1, 1, 99.99, '2026-02-16 10:00:00', '2026-02-16 10:00:00'),"
        "(2, 2, 49.50, '2026-02-16 11:00:00', '2026-02-16 11:00:00'),"
        "(3, 1, 25.00, '2026-02-15 09:00:00', '2026-02-15 09:00:00')"
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
