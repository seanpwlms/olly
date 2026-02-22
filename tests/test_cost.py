"""Tests for cost checking, cost state persistence, and cost summary."""

from __future__ import annotations

from typing import Any, cast

from olly.checks.cost import check_cost, summarize_costs, _detect_cost_anomalies
from olly.config import ConnectionConfig, CostConfig, NamedConnection, OllyConfig, Selection
from olly.models import CostRecord
from olly.state import StateDB
from conftest import make_cost_record, FakeAdapter


def test_check_cost_success(tmp_path):
    """Adapter with fetch_query_costs returns records."""
    expected = [make_cost_record()]
    adapter = FakeAdapter(cost_records=expected)

    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        records, findings = check_cost(cast(Any, adapter), ["main"], CostConfig(), db)
    assert records == expected
    assert findings == []


def test_check_cost_exception(tmp_path):
    """Adapter that raises returns empty results."""
    adapter = FakeAdapter(raise_on_fetch=True)

    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        records, findings = check_cost(cast(Any, adapter), ["main"], CostConfig(), db)
    assert records == []
    assert findings == []


def test_detect_cost_anomalies_spike(tmp_path):
    """Detects a cost spike when z-score exceeds threshold."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        # Seed historical cost data: 5 snapshots with slight variation
        for i, cost in enumerate([9.0, 10.0, 11.0, 10.0, 10.0]):
            sid = db.create_snapshot()
            db.store_cost_data(sid, [make_cost_record(cost=cost)])

        # Current cost is way above average
        current = [make_cost_record(cost=100.0)]
        findings = _detect_cost_anomalies(current, db, spike_threshold=2.0)
    assert len(findings) == 1
    assert "spike" in findings[0].description.lower()


def test_detect_cost_anomalies_no_spike(tmp_path):
    """No finding when cost is within normal range."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        for cost in [9.0, 10.0, 11.0, 10.0, 10.0]:
            sid = db.create_snapshot()
            db.store_cost_data(sid, [make_cost_record(cost=cost)])

        current = [make_cost_record(cost=10.5)]
        findings = _detect_cost_anomalies(current, db, spike_threshold=3.0)
    assert findings == []


def test_detect_cost_anomalies_zero_current(tmp_path):
    """Zero current cost returns no findings."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        findings = _detect_cost_anomalies([], db, spike_threshold=3.0)
    assert findings == []


def test_detect_cost_anomalies_insufficient_history(tmp_path):
    """Fewer than 3 historical points returns no findings."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        sid = db.create_snapshot()
        db.store_cost_data(sid, [make_cost_record(cost=10.0)])
        current = [make_cost_record(cost=100.0)]
        findings = _detect_cost_anomalies(current, db, spike_threshold=2.0)
    assert findings == []


def test_detect_cost_anomalies_zero_stddev(tmp_path):
    """All identical history -> stddev=0 -> no division error."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        for _ in range(5):
            sid = db.create_snapshot()
            db.store_cost_data(sid, [make_cost_record(cost=10.0)])
        current = [make_cost_record(cost=10.0)]
        findings = _detect_cost_anomalies(current, db, spike_threshold=3.0)
    assert len(findings) == 0


def test_summarize_costs():
    """Summarizes costs by table and user."""
    records = [
        make_cost_record(schema="main", table="orders", cost=10.0),
        make_cost_record(schema="main", table="orders", cost=5.0),
        make_cost_record(schema="main", table="customers", cost=3.0),
    ]
    summary = summarize_costs(records)
    assert summary["total_cost_usd"] == 18.0
    assert len(summary["top_tables"]) == 2
    assert summary["top_tables"][0]["table"] == "orders"
    assert len(summary["top_users"]) == 1


# --- StateDB cost methods ---


def test_state_save_and_get_cost_history(tmp_path):
    """Cost data can be saved and retrieved via history."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        sid = db.create_snapshot()
        records = [make_cost_record(cost=25.0), make_cost_record(table="customers", cost=15.0)]
        db.store_cost_data(sid, records)

        history = db.get_cost_history(depth=10)
    assert len(history) == 1
    assert history[0][1] == 40.0  # 25 + 15


def test_state_get_cost_records_for_snapshot(tmp_path):
    """Cost records can be retrieved for a specific snapshot."""
    state_path = tmp_path / "state.db"
    with StateDB(state_path) as db:
        db.init_db()
        sid = db.create_snapshot()
        db.store_cost_data(sid, [make_cost_record(cost=7.5)])

        loaded = db.get_cost_records_for_snapshot(sid)
    assert len(loaded) == 1
    assert loaded[0].estimated_cost_usd == 7.5
    assert loaded[0].schema_name == "main"


def test_state_db_creates_cost_table(tmp_path):
    """Verify that init_db creates the cost_snapshot table."""
    with StateDB(db_path=tmp_path / "state.db") as db:
        db.init_db()
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cost_snapshot'"
        ).fetchall()
        assert len(tables) == 1


# --- Config parsing tests ---


def test_config_parse_cost_section(tmp_path):
    from olly.config import load_config

    config_path = tmp_path / "olly.toml"
    config_path.write_text(
        '[connection]\ntype = "duckdb"\npath = "test.db"\n\n'
        "[cost]\n"
        "enabled = true\n"
        "lookback_days = 14\n"
        'bigquery_region = "eu"\n'
        "price_per_tb_usd = 5.0\n"
        "spike_threshold = 2.5\n"
    )
    config = load_config(config_path)
    assert config.cost.enabled is True
    assert config.cost.lookback_days == 14
    assert config.cost.bigquery_region == "eu"
    assert config.cost.price_per_tb_usd == 5.0
    assert config.cost.spike_threshold == 2.5


def test_config_default_cost(tmp_path):
    from olly.config import load_config

    config_path = tmp_path / "olly.toml"
    config_path.write_text('[connection]\ntype = "duckdb"\npath = "test.db"\n')
    config = load_config(config_path)
    assert config.cost.enabled is False
    assert config.cost.lookback_days == 30
    assert config.cost.price_per_tb_usd == 6.25


def test_config_write_cost(tmp_path):
    from olly.config import load_config, write_config

    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path="test.db"),
        selection=Selection(),
    )
    config = OllyConfig(
        connections={"primary": nc},
        cost=CostConfig(enabled=True, lookback_days=7, bigquery_region="eu"),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)

    loaded = load_config(path)
    assert loaded.cost.enabled is True
    assert loaded.cost.lookback_days == 7
    assert loaded.cost.bigquery_region == "eu"


# --- BigQuery adapter tests ---


def test_fetch_query_costs_adapter():
    """Test that fetch_query_costs builds correct SQL and parses results."""

    class MockRow:
        def __init__(self, vals):
            self._vals = vals

        def values(self):
            return self._vals

    class MockConnection:
        def __init__(self):
            self.last_sql: str | None = None

        def raw_sql(self, sql):
            self.last_sql = sql
            return [
                MockRow(("analytics", "events", "user@co.com", 2199023255552, 5)),
                MockRow(("analytics", "users", "admin@co.com", 549755813888, 2)),
            ]

    from olly.adapters.bigquery import BigQueryAdapter

    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    mock_conn = MockConnection()
    adapter._conn = mock_conn

    records = adapter.fetch_query_costs(
        schemas=["analytics"],
        lookback_days=30,
        region="us",
        price_per_tb_usd=6.25,
    )

    assert len(records) == 2
    assert records[0].schema_name == "analytics"
    assert records[0].table_name == "events"
    assert records[0].user_email == "user@co.com"
    assert records[0].total_bytes_billed == 2199023255552
    assert records[0].estimated_cost_usd == 2199023255552 / 1099511627776 * 6.25
    assert records[0].query_count == 5
    assert mock_conn.last_sql is not None
    assert "INFORMATION_SCHEMA.JOBS_BY_PROJECT" in mock_conn.last_sql
    assert "'analytics'" in mock_conn.last_sql


def test_fetch_query_costs_empty_schemas():
    from olly.adapters.bigquery import BigQueryAdapter

    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    records = adapter.fetch_query_costs(schemas=[], lookback_days=30)
    assert records == []


def test_summarize_costs_top_limits():
    """Top tables limited to 10, top users limited to 5."""
    records = [
        _makemake_cost_record(table=f"table_{i}", cost=float(i), user=f"user_{i}@co.com")
        for i in range(15)
    ]
    summary = summarize_costs(records)
    assert len(summary["top_tables"]) == 10
    assert len(summary["top_users"]) == 5


def _makemake_cost_record(
    schema: str = "main",
    table: str = "orders",
    user: str = "user@example.com",
    bytes_billed: int = 1099511627776,
    cost: float = 6.25,
    query_count: int = 10,
) -> CostRecord:
    return CostRecord(
        schema_name=schema,
        table_name=table,
        user_email=user,
        total_bytes_billed=bytes_billed,
        estimated_cost_usd=cost,
        query_count=query_count,
    )
