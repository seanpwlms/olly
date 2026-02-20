from __future__ import annotations

from datetime import datetime

import pytest

from olly.adapters.bigquery import BigQueryAdapter
from olly.models import TableInfo


# ---------------------------------------------------------------------------
# Stubs for unit-testing without a real BigQuery connection
# ---------------------------------------------------------------------------


class _FakeType:
    """Minimal stand-in for an Ibis data type."""

    def __init__(self, type_str: str, *, nullable: bool = True):
        self._type_str = type_str
        self.nullable = nullable

    def __str__(self) -> str:
        return self._type_str


class _StubSchema:
    def __init__(self, columns: dict[str, _FakeType]):
        self._columns = columns

    def items(self):
        return self._columns.items()


class _StubExecutable:
    def __init__(self, val):
        self._val = val

    def execute(self):
        return self._val


class _StubColumn:
    def __init__(self, max_val):
        self._max_val = max_val

    def max(self):
        return _StubExecutable(self._max_val)


class _StubTable:
    def __init__(
        self,
        columns: dict[str, _FakeType],
        *,
        count_val: int = 0,
        max_val: object = None,
    ):
        self._schema = _StubSchema(columns)
        self._count_val = count_val
        self._max_val = max_val

    def schema(self):
        return self._schema

    def count(self):
        return _StubExecutable(self._count_val)

    def __getitem__(self, key: str):
        return _StubColumn(self._max_val)


class _StubResult:
    def __init__(self, rows: list):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _StubConn:
    def __init__(
        self,
        *,
        raw_sql_rows: list[list] | None = None,
        tables: dict[tuple[str, str], _StubTable] | None = None,
        table_names: dict[str, list[str]] | None = None,
        schemas: list[str] | None = None,
    ):
        self._raw_sql_rows = list(raw_sql_rows or [])
        self._tables = tables or {}
        self._table_names = table_names or {}
        self._schemas = schemas or []
        self.queries: list[str] = []

    def raw_sql(self, sql: str):
        self.queries.append(sql)
        rows = self._raw_sql_rows.pop(0) if self._raw_sql_rows else []
        return _StubResult(rows)

    def list_tables(self, schema: str | None = None) -> list[str]:
        if schema is None:
            return []
        return self._table_names.get(schema, [])

    def table(self, name: str, schema: str | None = None) -> _StubTable | None:
        if schema is None:
            return None
        return self._tables.get((schema, name))

    def list_schemas(self):
        return self._schemas


def _make_adapter(
    *,
    raw_sql_rows: list[list] | None = None,
    tables: dict[tuple[str, str], _StubTable] | None = None,
    table_names: dict[str, list[str]] | None = None,
    schemas: list[str] | None = None,
    use_info_schema_row_counts: bool = True,
) -> BigQueryAdapter:
    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    adapter._conn = _StubConn(
        raw_sql_rows=raw_sql_rows,
        tables=tables,
        table_names=table_names,
        schemas=schemas,
    )
    adapter._use_information_schema_row_counts = use_info_schema_row_counts
    return adapter


def _make_error_adapter() -> BigQueryAdapter:
    class _ErrorConn:
        def raw_sql(self, sql: str):
            raise Exception("connection lost")

        def table(self, name, schema=None):
            raise Exception("connection lost")

        def list_tables(self, schema=None):
            raise Exception("connection lost")

    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    adapter._conn = _ErrorConn()
    adapter._use_information_schema_row_counts = True
    return adapter


# ---------------------------------------------------------------------------
# Helpers: _quote_identifier, _format_table, _build_row_expr
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_quote_identifier_uses_backticks(self):
        assert _make_adapter()._quote_identifier("col") == "`col`"

    def test_format_table(self):
        assert _make_adapter()._format_table("dataset", "orders") == "`dataset.orders`"

    def test_build_row_expr_single_column(self):
        result = _make_adapter()._build_row_expr(["id"])
        assert result == "CONCAT(COALESCE(CAST(`id` AS STRING), ''))"

    def test_build_row_expr_multiple_columns(self):
        result = _make_adapter()._build_row_expr(["id", "name"])
        assert result == (
            "CONCAT(COALESCE(CAST(`id` AS STRING), ''), '|', "
            "COALESCE(CAST(`name` AS STRING), ''))"
        )


# ---------------------------------------------------------------------------
# list_schemas
# ---------------------------------------------------------------------------


class TestListSchemas:
    def test_delegates_to_conn(self):
        adapter = _make_adapter(schemas=["dataset1", "dataset2"])
        assert adapter.list_schemas() == ["dataset1", "dataset2"]


# ---------------------------------------------------------------------------
# _fetch_table_metadata
# ---------------------------------------------------------------------------


class TestFetchTableMetadata:
    def test_returns_metadata_dict(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("orders", "BASE TABLE", 100), ("users", "VIEW", None)],
            ],
        )
        metadata = adapter._fetch_table_metadata("analytics")
        assert metadata["orders"] == {"table_type": "BASE TABLE", "row_count": 100}
        assert metadata["users"] == {"table_type": "VIEW", "row_count": None}

    def test_sql_uses_backtick_quoting(self):
        adapter = _make_adapter(raw_sql_rows=[[]])
        adapter._fetch_table_metadata("analytics")
        assert "`analytics.INFORMATION_SCHEMA.TABLES`" in adapter._conn.queries[0]

    def test_error_raises_runtime_error(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to read table metadata"):
            adapter._fetch_table_metadata("analytics")


# ---------------------------------------------------------------------------
# _get_table_type
# ---------------------------------------------------------------------------


class TestGetTableType:
    def test_returns_table(self):
        adapter = _make_adapter(raw_sql_rows=[[("BASE TABLE",)]])
        assert adapter._get_table_type("analytics", "orders") == "TABLE"

    def test_returns_view(self):
        adapter = _make_adapter(raw_sql_rows=[[("VIEW",)]])
        assert adapter._get_table_type("analytics", "my_view") == "VIEW"

    def test_defaults_to_table_on_empty_result(self):
        adapter = _make_adapter(raw_sql_rows=[[]])
        assert adapter._get_table_type("analytics", "orders") == "TABLE"

    def test_sql_uses_backtick_quoting(self):
        adapter = _make_adapter(raw_sql_rows=[[("TABLE",)]])
        adapter._get_table_type("analytics", "orders")
        assert "`analytics.INFORMATION_SCHEMA.TABLES`" in adapter._conn.queries[0]

    def test_error_raises_runtime_error(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to read table type"):
            adapter._get_table_type("analytics", "orders")


# ---------------------------------------------------------------------------
# fetch_schema_info
# ---------------------------------------------------------------------------


class TestFetchSchemaInfo:
    def test_builds_table_infos(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("orders", "BASE TABLE", 100)],
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable(
                    {
                        "id": _FakeType("INT64", nullable=False),
                        "amount": _FakeType("FLOAT64", nullable=True),
                    }
                ),
            },
        )
        tables = adapter.fetch_schema_info(["analytics"])
        assert len(tables) == 1
        assert tables[0].schema_name == "analytics"
        assert tables[0].table_name == "orders"
        assert tables[0].table_type == "BASE TABLE"
        assert len(tables[0].columns) == 2
        assert tables[0].columns[0].column_name == "id"
        assert tables[0].columns[0].is_nullable is False
        assert tables[0].columns[1].column_name == "amount"
        assert tables[0].columns[1].is_nullable is True

    def test_falls_back_to_get_table_type_when_metadata_is_none(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("orders", None, 100)],  # table_type is None
                [("BASE TABLE",)],  # _get_table_type fallback
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        tables = adapter.fetch_schema_info(["analytics"])
        assert tables[0].table_type == "TABLE"

    def test_falls_back_when_table_not_in_metadata(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [],  # _fetch_table_metadata returns no rows
                [("BASE TABLE",)],  # _get_table_type fallback
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        tables = adapter.fetch_schema_info(["analytics"])
        assert tables[0].table_type == "TABLE"

    def test_view_type_from_metadata(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("my_view", "VIEW", None)],
            ],
            table_names={"analytics": ["my_view"]},
            tables={
                ("analytics", "my_view"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        tables = adapter.fetch_schema_info(["analytics"])
        assert tables[0].table_type == "VIEW"


# ---------------------------------------------------------------------------
# SQL generation: fetch_count, fetch_count_distinct, fetch_hash
# ---------------------------------------------------------------------------


class TestFetchCount:
    def test_with_where(self):
        adapter = _make_adapter(raw_sql_rows=[[(3,)]])
        assert adapter.fetch_count("dataset", "orders", "amount >= 10") == 3
        assert adapter._conn.queries == [
            "SELECT COUNT(*) FROM `dataset.orders` WHERE amount >= 10"
        ]

    def test_without_where(self):
        adapter = _make_adapter(raw_sql_rows=[[(7,)]])
        assert adapter.fetch_count("dataset", "orders", None) == 7
        assert "WHERE" not in adapter._conn.queries[0]


class TestFetchCountDistinct:
    def test_sql(self):
        adapter = _make_adapter(raw_sql_rows=[[(2,)]])
        count = adapter.fetch_count_distinct(
            "dataset",
            "orders",
            "customer_id",
            "updated_at >= '2026-02-15 00:00:00'",
        )
        assert count == 2
        assert adapter._conn.queries == [
            "SELECT COUNT(DISTINCT `customer_id`) FROM `dataset.orders` "
            "WHERE updated_at >= '2026-02-15 00:00:00'"
        ]


class TestFetchHash:
    def test_bigquery_syntax(self):
        adapter = _make_adapter(raw_sql_rows=[[("abc123",)]])
        value = adapter.fetch_hash(
            "dataset",
            "orders",
            ["id", "amount"],
            "id",
            "updated_at >= '2026-02-15 00:00:00'",
        )
        assert value == "abc123"
        query = adapter._conn.queries[0]
        assert "TO_HEX(MD5(STRING_AGG" in query
        assert "ORDER BY order_col" in query
        assert "FROM `dataset.orders`" in query

    def test_without_where(self):
        adapter = _make_adapter(raw_sql_rows=[[("def456",)]])
        adapter.fetch_hash("dataset", "orders", ["id"], "id", None)
        assert "WHERE" not in adapter._conn.queries[0]


# ---------------------------------------------------------------------------
# fetch_row_counts
# ---------------------------------------------------------------------------


class TestFetchRowCounts:
    def test_information_schema_mode(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("orders", "BASE TABLE", 42)],
            ],
            use_info_schema_row_counts=True,
        )
        infos = [
            TableInfo(
                schema_name="analytics",
                table_name="orders",
                table_type="TABLE",
                columns=[],
            ),
        ]
        records = adapter.fetch_row_counts(infos)
        assert len(records) == 1
        assert records[0].row_count == 42

    def test_count_star_mode(self):
        adapter = _make_adapter(
            tables={("analytics", "orders"): _StubTable({}, count_val=55)},
            use_info_schema_row_counts=False,
        )
        infos = [
            TableInfo(
                schema_name="analytics",
                table_name="orders",
                table_type="TABLE",
                columns=[],
            ),
        ]
        records = adapter.fetch_row_counts(infos)
        assert len(records) == 1
        assert records[0].row_count == 55

    def test_skips_views_in_info_schema_mode(self):
        adapter = _make_adapter(use_info_schema_row_counts=True)
        infos = [
            TableInfo(
                schema_name="analytics", table_name="v1", table_type="VIEW", columns=[]
            ),
        ]
        assert adapter.fetch_row_counts(infos) == []

    def test_skips_views_in_count_star_mode(self):
        adapter = _make_adapter(use_info_schema_row_counts=False)
        infos = [
            TableInfo(
                schema_name="analytics", table_name="v1", table_type="VIEW", columns=[]
            ),
        ]
        assert adapter.fetch_row_counts(infos) == []

    def test_info_schema_missing_row_count_raises(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("other_table", "BASE TABLE", 10)],
            ],
            use_info_schema_row_counts=True,
        )
        infos = [
            TableInfo(
                schema_name="analytics",
                table_name="orders",
                table_type="TABLE",
                columns=[],
            ),
        ]
        with pytest.raises(RuntimeError, match="Missing row count"):
            adapter.fetch_row_counts(infos)

    def test_count_star_error_raises(self):
        adapter = _make_error_adapter()
        adapter._use_information_schema_row_counts = False
        infos = [
            TableInfo(
                schema_name="analytics",
                table_name="orders",
                table_type="TABLE",
                columns=[],
            ),
        ]
        with pytest.raises(RuntimeError, match="Failed to fetch row count"):
            adapter.fetch_row_counts(infos)

    def test_caches_metadata_per_schema(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("t1", "TABLE", 10), ("t2", "TABLE", 20)],
            ],
            use_info_schema_row_counts=True,
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name="t1", table_type="TABLE", columns=[]
            ),
            TableInfo(
                schema_name="analytics", table_name="t2", table_type="TABLE", columns=[]
            ),
        ]
        records = adapter.fetch_row_counts(infos)
        assert len(records) == 2
        assert records[0].row_count == 10
        assert records[1].row_count == 20
        # Only one raw_sql call for metadata, not two
        assert len(adapter._conn.queries) == 1


# ---------------------------------------------------------------------------
# fetch_max_timestamp
# ---------------------------------------------------------------------------


class TestFetchMaxTimestamp:
    def test_returns_none_on_null(self):
        adapter = _make_adapter(
            tables={("analytics", "orders"): _StubTable({}, max_val=None)},
        )
        assert adapter.fetch_max_timestamp("analytics", "orders", "updated_at") is None

    def test_returns_datetime(self):
        ts = datetime(2026, 1, 15, 12, 0, 0)
        adapter = _make_adapter(
            tables={("analytics", "orders"): _StubTable({}, max_val=ts)},
        )
        assert adapter.fetch_max_timestamp("analytics", "orders", "updated_at") == ts

    def test_converts_pandas_timestamp(self):
        ts = datetime(2026, 1, 15, 12, 0, 0)

        class _PandasTimestamp:
            def to_pydatetime(self):
                return ts

        adapter = _make_adapter(
            tables={
                ("analytics", "orders"): _StubTable({}, max_val=_PandasTimestamp())
            },
        )
        assert adapter.fetch_max_timestamp("analytics", "orders", "updated_at") == ts

    def test_error_raises(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to fetch max timestamp"):
            adapter.fetch_max_timestamp("analytics", "orders", "updated_at")


# ---------------------------------------------------------------------------
# fetch_table_usage
# ---------------------------------------------------------------------------


class TestFetchTableUsage:
    def test_empty_schemas(self):
        adapter = _make_adapter()
        assert adapter.fetch_table_usage([], 30) == []

    def test_returns_usage_records(self):
        ts = datetime(2026, 2, 10, 12, 0, 0)
        adapter = _make_adapter(
            raw_sql_rows=[
                [("analytics", "orders", ts)],  # JOBS_BY_PROJECT
                [
                    ("orders", "BASE TABLE", 100)
                ],  # _fetch_table_metadata via fetch_schema_info
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        records = adapter.fetch_table_usage(["analytics"], 30)
        assert len(records) == 1
        assert records[0].schema_name == "analytics"
        assert records[0].table_name == "orders"
        assert records[0].last_queried_at == ts

    def test_unqueried_table_has_none(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [],  # JOBS_BY_PROJECT returns nothing
                [("orders", "BASE TABLE", 100)],  # _fetch_table_metadata
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        records = adapter.fetch_table_usage(["analytics"], 30)
        assert len(records) == 1
        assert records[0].last_queried_at is None

    def test_null_last_queried_at_treated_as_unqueried(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("analytics", "orders", None)],  # queried_at is None
                [("orders", "BASE TABLE", 100)],
            ],
            table_names={"analytics": ["orders"]},
            tables={
                ("analytics", "orders"): _StubTable({"id": _FakeType("INT64")}),
            },
        )
        records = adapter.fetch_table_usage(["analytics"], 30)
        assert records[0].last_queried_at is None

    def test_sql_contains_region(self):
        adapter = _make_adapter(
            raw_sql_rows=[[], []],
            table_names={"analytics": []},
        )
        adapter.fetch_table_usage(["analytics"], 30, region="eu")
        assert "region-eu" in adapter._conn.queries[0]

    def test_error_raises(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to fetch table usage"):
            adapter.fetch_table_usage(["analytics"], 30)


# ---------------------------------------------------------------------------
# fetch_query_costs
# ---------------------------------------------------------------------------


class TestFetchQueryCosts:
    def test_empty_schemas(self):
        adapter = _make_adapter()
        assert adapter.fetch_query_costs([], 30) == []

    def test_returns_cost_records(self):
        bytes_per_tb = 1099511627776
        adapter = _make_adapter(
            raw_sql_rows=[
                [("analytics", "orders", "user@example.com", bytes_per_tb, 5)],
            ],
        )
        records = adapter.fetch_query_costs(["analytics"], 30)
        assert len(records) == 1
        assert records[0].schema_name == "analytics"
        assert records[0].table_name == "orders"
        assert records[0].user_email == "user@example.com"
        assert records[0].total_bytes_billed == bytes_per_tb
        assert records[0].estimated_cost_usd == pytest.approx(6.25)
        assert records[0].query_count == 5

    def test_null_bytes_treated_as_zero(self):
        adapter = _make_adapter(
            raw_sql_rows=[
                [("analytics", "orders", "user@example.com", None, 1)],
            ],
        )
        records = adapter.fetch_query_costs(["analytics"], 30)
        assert records[0].total_bytes_billed == 0
        assert records[0].estimated_cost_usd == 0.0

    def test_custom_price_per_tb(self):
        bytes_per_tb = 1099511627776
        adapter = _make_adapter(
            raw_sql_rows=[
                [("analytics", "orders", "user@example.com", bytes_per_tb, 1)],
            ],
        )
        records = adapter.fetch_query_costs(["analytics"], 30, price_per_tb_usd=10.0)
        assert records[0].estimated_cost_usd == pytest.approx(10.0)

    def test_sql_contains_region(self):
        adapter = _make_adapter(raw_sql_rows=[[]])
        adapter.fetch_query_costs(["analytics"], 30, region="eu")
        assert "region-eu" in adapter._conn.queries[0]

    def test_error_raises(self):
        adapter = _make_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to fetch query costs"):
            adapter.fetch_query_costs(["analytics"], 30)
