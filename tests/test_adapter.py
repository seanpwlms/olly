from olly.adapter import connect_typed
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
    """Max timestamp should be recent (within last 3 days from test data)."""
    from datetime import datetime, timedelta

    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    ts = backend.fetch_max_timestamp("main", "orders", "updated_at")
    assert ts is not None
    # Test data uses relative timestamps (now, 1 day ago, 2 days ago)
    # So max timestamp should be within last 3 days
    assert ts > datetime.now() - timedelta(days=3)
    assert ts <= datetime.now() + timedelta(minutes=5)  # Allow small clock drift


def test_fetch_count_with_where(olly_config):
    """Test fetch_count with WHERE clause filtering."""
    from datetime import datetime, timedelta

    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    # Test data has 3 orders: now, 1 day ago, 2 days ago
    # Filter for orders within last 1.5 days (should get 2)
    cutoff = (datetime.now() - timedelta(days=1, hours=12)).strftime('%Y-%m-%d %H:%M:%S')
    count = backend.fetch_count(
        "main", "orders", f"amount >= 49.5 AND updated_at >= '{cutoff}'"
    )
    assert count == 2


def test_fetch_count_distinct(olly_config):
    """Test COUNT(DISTINCT) with relative date filter."""
    from datetime import datetime, timedelta

    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    # Test data has orders from last 3 days - get all of them
    start = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    end = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    count = backend.fetch_count_distinct(
        "main",
        "orders",
        "customer_id",
        f"updated_at >= '{start}' AND updated_at <= '{end}'",
    )
    assert count == 2


def test_fetch_hash(olly_config):
    """Test hash calculation is deterministic with relative dates."""
    from datetime import datetime, timedelta

    conn = olly_config.connections["primary"].connection
    backend = connect_typed(conn)
    # Use a filter that captures all test data
    start = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    end = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    where_sql = f"updated_at >= '{start}' AND updated_at <= '{end}'"

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
