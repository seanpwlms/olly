from datetime import datetime
from typing import Any, cast

import pytest

from olly.adapters.snowflake import SnowflakeAdapter, _split_schema
from olly.models import TableInfo
from helpers import (
    make_snowflake_adapter,
    make_snowflake_error_adapter,
)


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
        adapter = make_snowflake_adapter()
        assert (
            adapter._format_table("MYDB.PUBLIC", "orders") == '"MYDB"."PUBLIC"."orders"'
        )

    def test_format_table_quoting(self):
        adapter = make_snowflake_adapter()
        assert (
            adapter._format_table("my-db.my schema", "my table")
            == '"my-db"."my schema"."my table"'
        )

    def test_quote_identifier(self):
        assert make_snowflake_adapter()._quote_identifier("col") == '"col"'

    def test_build_row_expr_single(self):
        result = make_snowflake_adapter()._build_row_expr(["id"])
        assert result == "COALESCE(CAST(\"id\" AS VARCHAR), '')"

    def test_build_row_expr_multiple(self):
        result = make_snowflake_adapter()._build_row_expr(["id", "name"])
        assert "|| '|' ||" in result
        assert 'CAST("id" AS VARCHAR)' in result
        assert 'CAST("name" AS VARCHAR)' in result


# ---------------------------------------------------------------------------
# SQL generation: fetch_count, fetch_count_distinct, fetch_hash
# ---------------------------------------------------------------------------


class TestFetchCount:
    def test_without_where(self):
        adapter = make_snowflake_adapter(rows_per_call=[[(5,)]])
        assert adapter.fetch_count("MYDB.PUBLIC", "orders", None) == 5
        assert adapter._conn.queries == [
            'SELECT COUNT(*) FROM "MYDB"."PUBLIC"."orders"'
        ]

    def test_with_where(self):
        adapter = make_snowflake_adapter(rows_per_call=[[(2,)]])
        assert adapter.fetch_count("MYDB.PUBLIC", "orders", "amount >= 10") == 2
        assert "WHERE amount >= 10" in adapter._conn.queries[0]


class TestFetchCountDistinct:
    def test_sql(self):
        adapter = make_snowflake_adapter(rows_per_call=[[(3,)]])
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
        adapter = make_snowflake_adapter(rows_per_call=[[("abc123",)]])
        assert (
            adapter.fetch_hash("MYDB.PUBLIC", "orders", ["id", "amount"], "id", None)
            == "abc123"
        )
        query = adapter._conn.queries[0]
        assert "LISTAGG(row_hash, '')" in query
        assert "WITHIN GROUP (ORDER BY order_col)" in query

    def test_with_where(self):
        adapter = make_snowflake_adapter(rows_per_call=[[("def456",)]])
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
        adapter = make_snowflake_adapter(rows_per_call=[[(10,)]])
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
        adapter = make_snowflake_adapter(
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
        adapter = make_snowflake_error_adapter()
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
        adapter = make_snowflake_adapter(rows_per_call=[[(None,)]])
        assert adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at") is None

    def test_three_part_name_in_sql(self):
        adapter = make_snowflake_adapter(rows_per_call=[[(None,)]])
        adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at")
        assert '"DB"."SCH"."orders"' in adapter._conn.queries[0]

    def test_returns_datetime(self):
        ts = datetime(2026, 1, 15, 12, 0, 0)
        adapter = make_snowflake_adapter(rows_per_call=[[(ts,)]])
        assert adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at") == ts

    def test_error_raises(self):
        adapter = make_snowflake_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to fetch max timestamp"):
            adapter.fetch_max_timestamp("DB.SCH", "orders", "updated_at")


# ---------------------------------------------------------------------------
# list_schemas
# ---------------------------------------------------------------------------


class TestListSchemas:
    def test_account_usage_mode(self):
        adapter = make_snowflake_adapter(
            rows_per_call=[[("MYDB", "PUBLIC"), ("MYDB", "RAW")]],
            use_account_usage=True,
        )
        assert adapter.list_schemas() == ["MYDB.PUBLIC", "MYDB.RAW"]
        assert "ACCOUNT_USAGE.SCHEMATA" in adapter._conn.queries[0]

    def test_information_schema_mode(self):
        adapter = make_snowflake_adapter(
            rows_per_call=[
                [("ignored", "MYDB")],
                [("PUBLIC",), ("RAW",)],
            ],
        )
        assert adapter.list_schemas() == ["MYDB.PUBLIC", "MYDB.RAW"]
        assert "SHOW DATABASES" in adapter._conn.queries[0]

    def test_skips_inaccessible_db(self):
        from helpers import SnowflakeStubResult

        class _ErrorOnSecondConn:
            def __init__(self):
                self.queries: list[str] = []
                self._call_count = 0

            def raw_sql(self, sql):
                self.queries.append(sql)
                self._call_count += 1
                if self._call_count == 1:
                    return SnowflakeStubResult([("ignored", "DB1"), ("ignored", "DB2")])
                if self._call_count == 2:
                    return SnowflakeStubResult([("PUBLIC",)])
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
        adapter = make_snowflake_adapter(
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
        adapter = make_snowflake_adapter(
            rows_per_call=[
                [("MYDB", "PUBLIC", "v1", "VIEW")],
                [("MYDB", "PUBLIC", "v1", "id", "NUMBER", "NO")],
            ]
        )
        assert adapter.fetch_schema_info(["MYDB.PUBLIC"])[0].table_type == "VIEW"

    def test_account_usage_queries(self):
        adapter = make_snowflake_adapter(
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
            make_snowflake_error_adapter()._fetch_scalar("SELECT 1", "test")

    def test_scalar_str_error(self):
        with pytest.raises(RuntimeError, match="Failed to run query"):
            make_snowflake_error_adapter()._fetch_scalar_str("SELECT 1", "test")

    def test_scalar_null(self):
        assert make_snowflake_adapter(rows_per_call=[[(None,)]])._fetch_scalar("Q", "t") == 0

    def test_scalar_str_null(self):
        assert (
            make_snowflake_adapter(rows_per_call=[[(None,)]])._fetch_scalar_str("Q", "t") is None
        )

    def test_scalar_str_empty(self):
        assert make_snowflake_adapter(rows_per_call=[[]])._fetch_scalar_str("Q", "t") is None


# ---------------------------------------------------------------------------
# fetch_table_usage (ACCOUNT_USAGE.ACCESS_HISTORY)
# ---------------------------------------------------------------------------


class TestFetchTableUsage:
    def test_supports_usage_history_tracks_account_usage_flag(self):
        assert make_snowflake_adapter().SUPPORTS_USAGE_HISTORY is False
        assert (
            make_snowflake_adapter(use_account_usage=True).SUPPORTS_USAGE_HISTORY
            is True
        )

    def test_returns_records_with_none_for_unqueried_tables(self):
        ts = datetime(2026, 7, 1, 12, 0, 0)
        adapter = make_snowflake_adapter(
            rows_per_call=[
                # access history: only ORDERS was queried
                [("MYDB.PUBLIC.ORDERS", ts)],
                # fetch_schema_info: table metadata
                [
                    ("MYDB", "PUBLIC", "ORDERS", "BASE TABLE"),
                    ("MYDB", "PUBLIC", "DEAD", "BASE TABLE"),
                ],
                # fetch_schema_info: columns
                [
                    ("MYDB", "PUBLIC", "ORDERS", "ID", "NUMBER", "YES"),
                    ("MYDB", "PUBLIC", "DEAD", "ID", "NUMBER", "YES"),
                ],
            ],
            use_account_usage=True,
        )
        records = adapter.fetch_table_usage(["MYDB.PUBLIC"], lookback_days=90)
        by_table = {(r.schema_name, r.table_name): r.last_queried_at for r in records}
        assert by_table == {
            ("MYDB.PUBLIC", "ORDERS"): ts,
            ("MYDB.PUBLIC", "DEAD"): None,
        }

        usage_sql = adapter._conn.queries[0]
        assert "SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY" in usage_sql
        assert "DATEADD(DAY, -90, CURRENT_TIMESTAMP())" in usage_sql
        assert "IN ('MYDB.PUBLIC')" in usage_sql
        assert "LATERAL FLATTEN" in usage_sql

    def test_skips_malformed_object_names(self):
        ts = datetime(2026, 7, 1)
        adapter = make_snowflake_adapter(
            rows_per_call=[
                [("not_qualified", ts), ("MYDB.PUBLIC", ts)],
                [("MYDB", "PUBLIC", "T1", "BASE TABLE")],
                [("MYDB", "PUBLIC", "T1", "ID", "NUMBER", "YES")],
            ],
            use_account_usage=True,
        )
        records = adapter.fetch_table_usage(["MYDB.PUBLIC"], lookback_days=30)
        assert len(records) == 1
        assert records[0].last_queried_at is None

    def test_without_account_usage_returns_empty(self):
        adapter = make_snowflake_adapter()
        assert adapter.fetch_table_usage(["MYDB.PUBLIC"], lookback_days=90) == []
        assert adapter._conn.queries == []

    def test_empty_schemas_returns_empty(self):
        adapter = make_snowflake_adapter(use_account_usage=True)
        assert adapter.fetch_table_usage([], lookback_days=90) == []
        assert adapter._conn.queries == []

    def test_query_error_raises_runtime_error(self):
        adapter = make_snowflake_error_adapter()
        adapter._use_account_usage = True
        with pytest.raises(RuntimeError, match="ACCESS_HISTORY"):
            adapter.fetch_table_usage(["MYDB.PUBLIC"], lookback_days=90)
