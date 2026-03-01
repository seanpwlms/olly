from helpers import make_postgres_adapter


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
