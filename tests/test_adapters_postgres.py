from olly.adapters.postgres import PostgresAdapter


class _StubResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _StubConn:
    def __init__(self, rows):
        self._rows = list(rows)
        self.queries = []

    def raw_sql(self, sql):
        self.queries.append(sql)
        row = self._rows.pop(0) if self._rows else (None,)
        return _StubResult(row)


def _make_adapter(rows):
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter._conn = _StubConn(rows)
    return adapter


def test_postgres_fetch_count_sql():
    adapter = _make_adapter(rows=[(4,)])
    count = adapter.fetch_count("public", "orders", "amount >= 10")
    assert count == 4
    assert adapter._conn.queries == [
        'SELECT COUNT(*) FROM "public"."orders" WHERE amount >= 10'
    ]


def test_postgres_fetch_count_distinct_sql():
    adapter = _make_adapter(rows=[(2,)])
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
    adapter = _make_adapter(rows=[("abc123",)])
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
