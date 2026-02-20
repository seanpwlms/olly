from datetime import datetime
from typing import Any, cast

import pytest

from olly.adapters.snowflake import SnowflakeAdapter, _split_schema
from olly.models import TableInfo


# ---------------------------------------------------------------------------
# Stubs for unit-testing without a real Snowflake connection
# ---------------------------------------------------------------------------


class _StubResult:
    def __init__(self, rows):
        self._rows = list(rows)
        self.description = [("col",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _StubConn:
    def __init__(self, rows_per_call=None):
        self._rows_per_call = list(rows_per_call or [])
        self.queries: list[str] = []

    def raw_sql(self, sql):
        self.queries.append(sql)
        rows = self._rows_per_call.pop(0) if self._rows_per_call else []
        return _StubResult(rows)


def _make_adapter(rows_per_call=None, *, use_account_usage=False):
    adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
    adapter._conn = _StubConn(rows_per_call)
    adapter._use_account_usage = use_account_usage
    adapter._default_database = None
    return adapter


def _make_error_adapter():
    class _ErrorConn:
        def raw_sql(self, sql):
            raise Exception("connection lost")

    adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
    adapter._conn = _ErrorConn()
    adapter._use_account_usage = False
    adapter._default_database = None
    return adapter


# ---------------------------------------------------------------------------
# _split_schema
# ---------------------------------------------------------------------------


class TestSplitSchema:
    def test_valid(self):
        assert _split_schema("MYDB.PUBLIC") == ("MYDB", "PUBLIC")

    def test_valid_lowercase(self):
        assert _split_schema("analytics.raw") == ("analytics", "raw")

    def test_missing_dot(self):
        with pytest.raises(ValueError, match="Expected 'database.schema'"):
            _split_schema("just_a_name")

    def test_empty_database(self):
        with pytest.raises(ValueError, match="Expected 'database.schema'"):
            _split_schema(".PUBLIC")

    def test_empty_schema(self):
        with pytest.raises(ValueError, match="Expected 'database.schema'"):
            _split_schema("MYDB.")

    def test_multiple_dots(self):
        assert _split_schema("MYDB.PUBLIC.EXTRA") == ("MYDB", "PUBLIC.EXTRA")


# ---------------------------------------------------------------------------
# Helpers: _format_table, _quote_identifier, _build_row_expr
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_format_table_three_part(self):
        adapter = _make_adapter()
        assert (
            adapter._format_table("MYDB.PUBLIC", "orders") == '"MYDB"."PUBLIC"."orders"'
        )

    def test_format_table_quoting(self):
        adapter = _make_adapter()
        assert (
            adapter._format_table("my-db.my schema", "my table")
            == '"my-db"."my schema"."my table"'
        )

    def test_quote_identifier(self):
        assert _make_adapter()._quote_identifier("col") == '"col"'

    def test_build_row_expr_single(self):
        result = _make_adapter()._build_row_expr(["id"])
        assert result == "COALESCE(CAST(\"id\" AS VARCHAR), '')"

    def test_build_row_expr_multiple(self):
        result = _make_adapter()._build_row_expr(["id", "name"])
        assert "|| '|' ||" in result
        assert 'CAST("id" AS VARCHAR)' in result
        assert 'CAST("name" AS VARCHAR)' in result


# ---------------------------------------------------------------------------
# SQL generation: fetch_count, fetch_count_distinct, fetch_hash
# ---------------------------------------------------------------------------


class TestFetchCount:
    def test_without_where(self):
        adapter = _make_adapter(rows_per_call=[[(5,)]])
        assert adapter.fetch_count("MYDB.PUBLIC", "orders", None) == 5
        assert adapter._conn.queries == [
            'SELECT COUNT(*) FROM "MYDB"."PUBLIC"."orders"'
        ]

    def test_with_where(self):
        adapter = _make_adapter(rows_per_call=[[(2,)]])
        assert adapter.fetch_count("MYDB.PUBLIC", "orders", "amount >= 10") == 2
        assert "WHERE amount >= 10" in adapter._conn.queries[0]


class TestFetchCountDistinct:
    def test_sql(self):
        adapter = _make_adapter(rows_per_call=[[(3,)]])
        assert (
            adapter.fetch_count_distinct(
                "MYDB.PUBLIC", "orders", "customer_id", "amount > 0"
            )
            == 3
        )
        query = adapter._conn.queries[0]
        assert 'COUNT(DISTINCT "customer_id")' in query
        assert '"MYDB"."PUBLIC"."orders"' in query


class TestFetchHash:
    def test_uses_listagg(self):
        adapter = _make_adapter(rows_per_call=[[("abc123",)]])
        assert (
            adapter.fetch_hash("MYDB.PUBLIC", "orders", ["id", "amount"], "id", None)
            == "abc123"
        )
        query = adapter._conn.queries[0]
        assert "LISTAGG(row_hash, '')" in query
        assert "WITHIN GROUP (ORDER BY order_col)" in query

    def test_with_where(self):
        adapter = _make_adapter(rows_per_call=[[("def456",)]])
        assert (
            adapter.fetch_hash("MYDB.PUBLIC", "orders", ["id"], "id", "id > 0")
            == "def456"
        )
        assert "WHERE id > 0" in adapter._conn.queries[0]


# ---------------------------------------------------------------------------
# fetch_row_counts
# ---------------------------------------------------------------------------


class TestFetchRowCounts:
    def test_skips_views(self):
        adapter = _make_adapter(rows_per_call=[[(10,)]])
        infos = [
            TableInfo(
                schema_name="DB.SCH", table_name="t1", table_type="TABLE", columns=[]
            ),
            TableInfo(
                schema_name="DB.SCH", table_name="v1", table_type="VIEW", columns=[]
            ),
        ]
        records = adapter.fetch_row_counts(infos)
        assert len(records) == 1
        assert records[0].table_name == "t1"
        assert records[0].row_count == 10

    def test_account_usage_mode(self):
        adapter = _make_adapter(
            rows_per_call=[[("DB", "SCH", "t1", 42)]],
            use_account_usage=True,
        )
        infos = [
            TableInfo(
                schema_name="DB.SCH", table_name="t1", table_type="TABLE", columns=[]
            ),
        ]
        records = adapter.fetch_row_counts(infos)
        assert records[0].row_count == 42
        assert "ACCOUNT_USAGE" in adapter._conn.queries[0]

    def test_error_raises(self):
        adapter = _make_error_adapter()
        infos = [
            TableInfo(
                schema_name="DB.SCH", table_name="t1", table_type="TABLE", columns=[]
            )
        ]
        with pytest.raises(RuntimeError, match="Failed to fetch row count"):
            adapter.fetch_row_counts(infos)


# ---------------------------------------------------------------------------
# fetch_max_timestamp
# ---------------------------------------------------------------------------


class TestFetchMaxTimestamp:
    def test_returns_none_on_null(self):
        adapter = _make_adapter(rows_per_call=[[(None,)]])
        assert adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at") is None

    def test_three_part_name_in_sql(self):
        adapter = _make_adapter(rows_per_call=[[(None,)]])
        adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at")
        assert '"DB"."SCH"."orders"' in adapter._conn.queries[0]

    def test_returns_datetime(self):
        ts = datetime(2026, 1, 15, 12, 0, 0)
        adapter = _make_adapter(rows_per_call=[[(ts,)]])
        assert adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at") == ts

    def test_error_raises(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to fetch max timestamp"):
            adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at")


# ---------------------------------------------------------------------------
# list_schemas
# ---------------------------------------------------------------------------


class TestListSchemas:
    def test_account_usage_mode(self):
        adapter = _make_adapter(
            rows_per_call=[[("MYDB", "PUBLIC"), ("MYDB", "RAW")]],
            use_account_usage=True,
        )
        assert adapter.list_schemas() == ["MYDB.PUBLIC", "MYDB.RAW"]
        assert "ACCOUNT_USAGE.SCHEMATA" in adapter._conn.queries[0]

    def test_information_schema_mode(self):
        adapter = _make_adapter(
            rows_per_call=[
                [("ignored", "MYDB")],
                [("PUBLIC",), ("RAW",)],
            ],
        )
        assert adapter.list_schemas() == ["MYDB.PUBLIC", "MYDB.RAW"]
        assert "SHOW DATABASES" in adapter._conn.queries[0]

    def test_skips_inaccessible_db(self):
        class _ErrorOnSecondConn:
            def __init__(self):
                self.queries: list[str] = []
                self._call_count = 0

            def raw_sql(self, sql):
                self.queries.append(sql)
                self._call_count += 1
                if self._call_count == 1:
                    return _StubResult([("ignored", "DB1"), ("ignored", "DB2")])
                if self._call_count == 2:
                    return _StubResult([("PUBLIC",)])
                raise RuntimeError("no access")

        adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
        adapter._conn = _ErrorOnSecondConn()
        adapter._use_account_usage = False
        adapter._default_database = None
        assert adapter.list_schemas() == ["DB1.PUBLIC"]


# ---------------------------------------------------------------------------
# fetch_schema_info
# ---------------------------------------------------------------------------


class TestFetchSchemaInfo:
    def test_builds_table_infos(self):
        adapter = _make_adapter(
            rows_per_call=[
                [("MYDB", "PUBLIC", "orders", "BASE TABLE")],
                [
                    ("MYDB", "PUBLIC", "orders", "id", "NUMBER", "NO"),
                    ("MYDB", "PUBLIC", "orders", "amount", "FLOAT", "YES"),
                ],
            ]
        )
        tables = adapter.fetch_schema_info(["MYDB.PUBLIC"])
        assert len(tables) == 1
        assert tables[0].schema_name == "MYDB.PUBLIC"
        assert tables[0].table_type == "TABLE"
        assert tables[0].columns[0].is_nullable is False
        assert tables[0].columns[1].is_nullable is True

    def test_view_type(self):
        adapter = _make_adapter(
            rows_per_call=[
                [("MYDB", "PUBLIC", "v1", "VIEW")],
                [("MYDB", "PUBLIC", "v1", "id", "NUMBER", "NO")],
            ]
        )
        assert adapter.fetch_schema_info(["MYDB.PUBLIC"])[0].table_type == "VIEW"

    def test_account_usage_queries(self):
        adapter = _make_adapter(
            rows_per_call=[
                [("MYDB", "PUBLIC", "t1", "BASE TABLE")],
                [("MYDB", "PUBLIC", "t1", "id", "NUMBER", "NO")],
            ],
            use_account_usage=True,
        )
        adapter.fetch_schema_info(["MYDB.PUBLIC"])
        assert "ACCOUNT_USAGE.TABLES" in adapter._conn.queries[0]
        assert "ACCOUNT_USAGE.COLUMNS" in adapter._conn.queries[1]


# ---------------------------------------------------------------------------
# fetch_table_schema
# ---------------------------------------------------------------------------


class TestFetchTableSchema:
    def test_returns_ibis_schema(self):
        import ibis
        import ibis.expr.datatypes as dt

        class _FakeTable:
            def schema(self):
                return ibis.Schema(cast(Any, {"id": dt.Int32(nullable=False), "name": dt.String(nullable=True)}))

        class _SchemaConn:
            def table(self, name, *, database=None, schema=None):
                return _FakeTable()

        adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
        adapter._conn = _SchemaConn()
        adapter._use_account_usage = False
        adapter._default_database = None
        result = adapter.fetch_table_schema("DB.SCH", "orders")
        assert list(result.names) == ["id", "name"]
        assert isinstance(result["id"], dt.Int32)
        assert isinstance(result["name"], dt.String)


# ---------------------------------------------------------------------------
# _fetch_scalar / _fetch_scalar_str edge cases
# ---------------------------------------------------------------------------


class TestScalarEdgeCases:
    def test_scalar_error(self):
        with pytest.raises(RuntimeError, match="Failed to run query"):
            _make_error_adapter()._fetch_scalar("SELECT 1", "test")

    def test_scalar_str_error(self):
        with pytest.raises(RuntimeError, match="Failed to run query"):
            _make_error_adapter()._fetch_scalar_str("SELECT 1", "test")

    def test_scalar_null(self):
        assert _make_adapter(rows_per_call=[[(None,)]])._fetch_scalar("Q", "t") == 0

    def test_scalar_str_null(self):
        assert (
            _make_adapter(rows_per_call=[[(None,)]])._fetch_scalar_str("Q", "t") is None
        )

    def test_scalar_str_empty(self):
        assert _make_adapter(rows_per_call=[[]])._fetch_scalar_str("Q", "t") is None
