import pytest

from olly.models import TableInfo
from helpers import PostgresStubResult, make_postgres_adapter


def _infos(*names, schema="public", table_type="TABLE"):
    return [
        TableInfo(schema_name=schema, table_name=n, table_type=table_type, columns=[])
        for n in names
    ]


class _CountingTable:
    def __init__(self, n):
        self._n = n

    def count(self):
        return self

    def execute(self):
        return self._n


def test_postgres_row_counts_default_to_count_star(monkeypatch):
    adapter = make_postgres_adapter()
    monkeypatch.setattr(adapter, "_get_ibis_table", lambda s, t: _CountingTable(9))
    records = adapter.fetch_row_counts(_infos("orders"))
    assert records[0].row_count == 9
    assert adapter._conn.queries == []


def test_postgres_metadata_row_counts_single_query():
    adapter = make_postgres_adapter(
        raw_sql_results=[
            PostgresStubResult([("public", "orders", 120), ("public", "events", 5)])
        ],
        use_information_schema_row_counts=True,
    )
    seen = []
    records = adapter.fetch_row_counts(
        _infos("orders", "events") + _infos("v", table_type="VIEW"),
        on_progress=lambda s, t: seen.append(t),
    )
    assert {r.table_name: r.row_count for r in records} == {"orders": 120, "events": 5}
    assert seen == ["orders", "events"]
    assert len(adapter._conn.queries) == 1
    sql = adapter._conn.queries[0]
    assert "n_live_tup" in sql
    assert "pg_inherits" in sql
    assert "COUNT(*)" not in sql
    assert "IN ('public')" in sql


def test_postgres_metadata_row_counts_skip_missing():
    adapter = make_postgres_adapter(
        raw_sql_results=[PostgresStubResult([("public", "orders", None)])],
        use_information_schema_row_counts=True,
    )
    assert adapter.fetch_row_counts(_infos("orders", "gone")) == []


def test_postgres_metadata_row_counts_escape_schema():
    adapter = make_postgres_adapter(use_information_schema_row_counts=True)
    adapter.fetch_row_counts(_infos("t", schema="o'brien"))
    assert "IN ('o''brien')" in adapter._conn.queries[0]


def test_postgres_metadata_row_counts_views_only_runs_no_query():
    adapter = make_postgres_adapter(use_information_schema_row_counts=True)
    assert adapter.fetch_row_counts(_infos("v", table_type="VIEW")) == []
    assert adapter._conn.queries == []


def test_postgres_metadata_row_counts_error_raises():
    adapter = make_postgres_adapter(use_information_schema_row_counts=True)

    def _boom(sql):
        raise Exception("permission denied")

    adapter._conn.raw_sql = _boom
    with pytest.raises(RuntimeError, match="pg_stat_user_tables"):
        adapter.fetch_row_counts(_infos("orders"))


def test_postgres_fetch_count_sql():
    adapter = make_postgres_adapter(rows=[(4,)])
    count = adapter.fetch_count("public", "orders", "amount >= 10")
    assert count == 4
    assert adapter._conn.queries == [
        'SELECT COUNT(*) FROM "public"."orders" WHERE amount >= 10'
    ]


def test_postgres_fetch_count_distinct_sql():
    adapter = make_postgres_adapter(rows=[(2,)])
    count = adapter.fetch_count_distinct(
        "public",
        "orders",
        "customer_id",
        "updated_at >= '2026-02-15 00:00:00'",
    )
    assert count == 2
    assert adapter._conn.queries == [
        'SELECT COUNT(DISTINCT "customer_id") FROM "public"."orders" '
        "WHERE updated_at >= '2026-02-15 00:00:00'"
    ]


def test_postgres_fetch_hash_sql():
    adapter = make_postgres_adapter(rows=[("abc123",)])
    value = adapter.fetch_hash(
        "public",
        "orders",
        ["id", "amount"],
        "id",
        "updated_at >= '2026-02-15 00:00:00'",
    )
    assert value == "abc123"
    query = adapter._conn.queries[0]
    assert "md5(string_agg" in query
    assert "ORDER BY order_col" in query
    assert 'FROM "public"."orders"' in query
