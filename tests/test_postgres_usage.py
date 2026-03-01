from __future__ import annotations

from datetime import datetime, timedelta, timezone

from olly.adapters.postgres import PostgresAdapter
from olly.models import ColumnInfo, TableInfo
from helpers import PostgresStubResult, make_postgres_adapter


def test_fetch_table_usage_empty_schemas():
    adapter = make_postgres_adapter()
    records = adapter.fetch_table_usage([], lookback_days=90)
    assert records == []


def test_fetch_table_usage_returns_records():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)

    pg_stat_rows = [("public", "orders", recent)]
    adapter = make_postgres_adapter(raw_sql_results=[PostgresStubResult(pg_stat_rows)])

    def fake_schema_info(schemas):
        return [
            TableInfo("public", "orders", "TABLE", [ColumnInfo("id", "int", False)]),
            TableInfo(
                "public", "unused_table", "TABLE", [ColumnInfo("id", "int", False)]
            ),
        ]

    adapter.fetch_schema_info = fake_schema_info  
    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 2

    by_table = {r.table_name: r for r in records}
    assert by_table["orders"].last_queried_at is not None
    assert by_table["unused_table"].last_queried_at is None


def test_fetch_table_usage_old_access_becomes_none():
    """Tables last accessed beyond lookback_days get last_queried_at=None."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=100)

    pg_stat_rows = [("public", "stale", old)]
    adapter = make_postgres_adapter(raw_sql_results=[PostgresStubResult(pg_stat_rows)])

    def fake_schema_info(schemas):
        return [TableInfo("public", "stale", "TABLE", [ColumnInfo("id", "int", False)])]

    adapter.fetch_schema_info = fake_schema_info  
    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 1
    assert records[0].last_queried_at is None


def test_fetch_table_usage_naive_timestamp():
    """Naive timestamps are treated as UTC."""
    now = datetime.now(timezone.utc)
    recent_naive = (now - timedelta(days=5)).replace(tzinfo=None)

    pg_stat_rows = [("public", "orders", recent_naive)]
    adapter = make_postgres_adapter(raw_sql_results=[PostgresStubResult(pg_stat_rows)])

    def fake_schema_info(schemas):
        return [
            TableInfo("public", "orders", "TABLE", [ColumnInfo("id", "int", False)])
        ]

    adapter.fetch_schema_info = fake_schema_info  
    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 1
    assert records[0].last_queried_at is not None


def test_fetch_table_usage_pg_lt_16_fallback(caplog):
    """PG < 16 where last_seq_scan column doesn't exist returns []."""
    adapter = PostgresAdapter.__new__(PostgresAdapter)

    class _FailConn:
        def raw_sql(self, sql: str):
            raise Exception('column "last_seq_scan" does not exist')

    adapter._conn = _FailConn()

    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert records == []
    assert "PostgreSQL 16+" in caplog.text


def test_fetch_table_usage_sql_structure():
    """Verify the generated SQL queries pg_stat_user_tables."""
    adapter = make_postgres_adapter(raw_sql_results=[PostgresStubResult([])])

    adapter.fetch_schema_info = lambda schemas: []  
    adapter.fetch_table_usage(["public", "analytics"], lookback_days=90)
    sql = adapter._conn.queries[0]
    assert "pg_stat_user_tables" in sql
    assert "'public'" in sql
    assert "'analytics'" in sql
    assert "GREATEST(last_seq_scan, last_idx_scan)" in sql


def test_fetch_table_usage_null_last_queried():
    """Tables with NULL last_seq_scan and last_idx_scan get None."""
    pg_stat_rows = [("public", "never_scanned", None)]
    adapter = make_postgres_adapter(raw_sql_results=[PostgresStubResult(pg_stat_rows)])

    def fake_schema_info(schemas):
        return [
            TableInfo(
                "public", "never_scanned", "TABLE", [ColumnInfo("id", "int", False)]
            )
        ]

    adapter.fetch_schema_info = fake_schema_info  
    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 1
    assert records[0].last_queried_at is None
