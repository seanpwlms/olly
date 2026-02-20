import pytest

from olly.adapter import connect_typed, connect_connection_string
from olly.config import Selection
from olly.config_ops import filter_table_infos


def test_connect(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    schemas = backend.list_schemas()
    assert "main" in schemas


def test_list_schemas(backend):
    schemas = backend.list_schemas()
    assert "main" in schemas
    assert "information_schema" in schemas


def test_fetch_schema_info(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    tables = backend.fetch_schema_info(["main"])

    names = {t.table_name for t in tables}
    assert "orders" in names
    assert "customers" in names
    assert "order_summary" in names

    orders = next(t for t in tables if t.table_name == "orders")
    assert orders.table_type == "TABLE"
    col_names = {c.column_name for c in orders.columns}
    assert "id" in col_names
    assert "amount" in col_names
    assert "updated_at" in col_names

    view = next(t for t in tables if t.table_name == "order_summary")
    assert view.table_type == "VIEW"


def test_fetch_schema_info_excludes_tables(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    tables = backend.fetch_schema_info(["main"])
    selection = Selection(
        include_schemas=["main"],
        include_tables=["main.*"],
        exclude_tables=["main.customers"],
    )
    olly_config.connections["primary"].selection = selection
    tables = filter_table_infos(selection, tables)

    names = {t.table_name for t in tables}
    assert "customers" not in names
    assert "orders" in names


def test_fetch_row_counts(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    tables = backend.fetch_schema_info(["main"])
    volumes = backend.fetch_row_counts(tables)

    vol_map = {v.table_name: v.row_count for v in volumes}
    assert vol_map["orders"] == 3
    assert vol_map["customers"] == 2
    # Views should be skipped
    assert "order_summary" not in vol_map


def test_fetch_max_timestamp(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    ts = backend.fetch_max_timestamp("main", "orders", "updated_at")
    assert ts is not None
    assert ts.year == 2026


def test_fetch_count_with_where(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    count = backend.fetch_count(
        "main", "orders", "amount >= 49.5 AND updated_at >= '2026-02-16 00:00:00'"
    )
    assert count == 2


def test_fetch_count_distinct(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    count = backend.fetch_count_distinct(
        "main",
        "orders",
        "customer_id",
        "updated_at >= '2026-02-15 00:00:00' AND updated_at <= '2026-02-16 23:59:59'",
    )
    assert count == 2


def test_fetch_hash(olly_config):
    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    where_sql = (
        "updated_at >= '2026-02-15 00:00:00' AND updated_at <= '2026-02-16 23:59:59'"
    )
    first = backend.fetch_hash(
        "main",
        "orders",
        ["id", "customer_id", "amount", "updated_at"],
        "id",
        where_sql,
    )
    second = backend.fetch_hash(
        "main",
        "orders",
        ["id", "customer_id", "amount", "updated_at"],
        "id",
        where_sql,
    )
    assert first is not None
    assert first == second


def test_duckdb_extras_forwarded(monkeypatch):
    """DuckDB extras are forwarded to the adapter constructor."""
    from olly.config import ConnectionConfig

    constructed_with: list[dict] = []

    class FakeDuckDBAdapter:
        def __init__(self, path=None, **kwargs):
            constructed_with.append({"path": path, **kwargs})

    monkeypatch.setattr("olly.adapters.duckdb.DuckDBAdapter", FakeDuckDBAdapter)
    conn = ConnectionConfig(
        type="duckdb", path="test.duckdb", extras={"read_only": True}
    )
    connect_typed(conn)
    assert len(constructed_with) == 1
    assert constructed_with[0]["read_only"] is True


def test_connect_unsupported_connection_string():
    """Unsupported prefix raises ConfigError."""
    from olly.config import ConfigError

    with pytest.raises(ConfigError, match="Cannot parse legacy connection string"):
        connect_connection_string("mysql://localhost/db")
