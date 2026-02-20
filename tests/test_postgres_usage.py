from __future__ import annotations

from datetime import datetime, timedelta, timezone

from olly.adapters.postgres import PostgresAdapter


class _StubResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _StubConn:
    """Minimal stand-in for an Ibis Postgres connection."""

    def __init__(self, raw_sql_results: list[_StubResult] | None = None):
        self.queries: list[str] = []
        self._results = list(raw_sql_results or [])

    def raw_sql(self, sql: str) -> _StubResult:
        self.queries.append(sql)
        if self._results:
            return self._results.pop(0)
        return _StubResult([])

    def list_tables(self, schema: str | None = None) -> list[str]:
        return []

    def table(self, name: str, schema: str | None = None):
        raise NotImplementedError


def _make_adapter(raw_sql_results: list[_StubResult] | None = None) -> PostgresAdapter:
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter._conn = _StubConn(raw_sql_results)
    return adapter


def test_fetch_table_usage_empty_schemas():
    adapter = _make_adapter()
    records = adapter.fetch_table_usage([], lookback_days=90)
    assert records == []


def test_fetch_table_usage_returns_records():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)

    pg_stat_rows = [("public", "orders", recent)]
    adapter = _make_adapter([_StubResult(pg_stat_rows)])

    # Monkey-patch fetch_schema_info to avoid real DB calls
    from olly.models import ColumnInfo, TableInfo

    def fake_schema_info(schemas):
        return [
            TableInfo("public", "orders", "TABLE", [ColumnInfo("id", "int", False)]),
            TableInfo(
                "public", "unused_table", "TABLE", [ColumnInfo("id", "int", False)]
            ),
        ]

    adapter.fetch_schema_info = fake_schema_info  # type: ignore[assignment]

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
    adapter = _make_adapter([_StubResult(pg_stat_rows)])

    from olly.models import ColumnInfo, TableInfo

    def fake_schema_info(schemas):
        return [TableInfo("public", "stale", "TABLE", [ColumnInfo("id", "int", False)])]

    adapter.fetch_schema_info = fake_schema_info  # type: ignore[assignment]

    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 1
    assert records[0].last_queried_at is None


def test_fetch_table_usage_naive_timestamp():
    """Naive timestamps are treated as UTC."""
    now = datetime.now(timezone.utc)
    recent_naive = (now - timedelta(days=5)).replace(tzinfo=None)

    pg_stat_rows = [("public", "orders", recent_naive)]
    adapter = _make_adapter([_StubResult(pg_stat_rows)])

    from olly.models import ColumnInfo, TableInfo

    def fake_schema_info(schemas):
        return [
            TableInfo("public", "orders", "TABLE", [ColumnInfo("id", "int", False)])
        ]

    adapter.fetch_schema_info = fake_schema_info  # type: ignore[assignment]

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
    adapter = _make_adapter([_StubResult([])])

    adapter.fetch_schema_info = lambda schemas: []  # type: ignore[assignment]

    adapter.fetch_table_usage(["public", "analytics"], lookback_days=90)
    sql = adapter._conn.queries[0]
    assert "pg_stat_user_tables" in sql
    assert "'public'" in sql
    assert "'analytics'" in sql
    assert "GREATEST(last_seq_scan, last_idx_scan)" in sql


def test_fetch_table_usage_null_last_queried():
    """Tables with NULL last_seq_scan and last_idx_scan get None."""
    pg_stat_rows = [("public", "never_scanned", None)]
    adapter = _make_adapter([_StubResult(pg_stat_rows)])

    from olly.models import ColumnInfo, TableInfo

    def fake_schema_info(schemas):
        return [
            TableInfo(
                "public", "never_scanned", "TABLE", [ColumnInfo("id", "int", False)]
            )
        ]

    adapter.fetch_schema_info = fake_schema_info  # type: ignore[assignment]

    records = adapter.fetch_table_usage(["public"], lookback_days=90)
    assert len(records) == 1
    assert records[0].last_queried_at is None
