"""Tests for BigQuery catalog metadata reads used by the freshness check."""

from __future__ import annotations

import pytest

from datetime import datetime, timezone

from olly.models import TableInfo
from helpers import make_bigquery_adapter, make_bigquery_error_adapter


class TestFetchTableMetadata:
    def test_returns_metadata_dict(self):
        adapter = make_bigquery_adapter(
            raw_sql_rows=[
                [("orders", "BASE TABLE", 100, None), ("users", "VIEW", None, None)],
            ],
        )
        metadata = adapter._fetch_table_metadata("analytics")
        assert metadata["orders"] == {
            "table_type": "BASE TABLE", "row_count": 100, "last_modified": None,
        }
        assert metadata["users"] == {
            "table_type": "VIEW", "row_count": None, "last_modified": None,
        }

    def test_sql_uses_backtick_quoting(self):
        adapter = make_bigquery_adapter(raw_sql_rows=[[]])
        adapter._fetch_table_metadata("analytics")
        assert "`analytics.INFORMATION_SCHEMA.TABLES`" in adapter._conn.queries[0]

    def test_error_raises_runtime_error(self):
        adapter = make_bigquery_error_adapter()
        with pytest.raises(RuntimeError, match="Failed to read table metadata"):
            adapter._fetch_table_metadata("analytics")


class TestFetchLastModified:
    def test_returns_last_modified_per_table(self):
        ts = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        adapter = make_bigquery_adapter(
            raw_sql_rows=[[("orders", "BASE TABLE", 100, ts)]],
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name="orders",
                table_type="TABLE", columns=[],
            )
        ]
        assert adapter.fetch_last_modified(infos) == {("analytics", "orders"): ts}

    def test_selects_storage_last_modified_time(self):
        adapter = make_bigquery_adapter(raw_sql_rows=[[]])
        adapter._fetch_table_metadata("analytics")
        assert "storage_last_modified_time" in adapter._conn.queries[0]

    def test_reuses_metadata_cache_without_extra_queries(self):
        """Freshness costs zero queries when the snapshot already warmed the cache."""
        ts = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        adapter = make_bigquery_adapter(
            raw_sql_rows=[[("t1", "TABLE", 10, ts), ("t2", "TABLE", 20, ts)]],
            use_info_schema_row_counts=True,
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name=n,
                table_type="TABLE", columns=[],
            )
            for n in ("t1", "t2")
        ]
        adapter.fetch_row_counts(infos)
        assert len(adapter._conn.queries) == 1
        result = adapter.fetch_last_modified(infos)
        assert len(result) == 2
        assert len(adapter._conn.queries) == 1  # no additional query

    def test_skips_views(self):
        adapter = make_bigquery_adapter(raw_sql_rows=[[]])
        infos = [
            TableInfo(
                schema_name="analytics", table_name="v1",
                table_type="VIEW", columns=[],
            )
        ]
        assert adapter.fetch_last_modified(infos) == {}
        assert adapter._conn.queries == []

    def test_null_last_modified_is_omitted(self):
        adapter = make_bigquery_adapter(
            raw_sql_rows=[[("orders", "BASE TABLE", 100, None)]],
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name="orders",
                table_type="TABLE", columns=[],
            )
        ]
        assert adapter.fetch_last_modified(infos) == {}

    def test_naive_timestamp_is_assumed_utc(self):
        adapter = make_bigquery_adapter(
            raw_sql_rows=[[("orders", "BASE TABLE", 100, datetime(2026, 3, 1, 12, 0))]],
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name="orders",
                table_type="TABLE", columns=[],
            )
        ]
        result = adapter.fetch_last_modified(infos)
        assert result[("analytics", "orders")].tzinfo is timezone.utc

    def test_iso_string_timestamp_is_parsed(self):
        adapter = make_bigquery_adapter(
            raw_sql_rows=[[("orders", "BASE TABLE", 100, "2026-03-01T12:00:00Z")]],
        )
        infos = [
            TableInfo(
                schema_name="analytics", table_name="orders",
                table_type="TABLE", columns=[],
            )
        ]
        result = adapter.fetch_last_modified(infos)
        assert result[("analytics", "orders")] == datetime(
            2026, 3, 1, 12, 0, tzinfo=timezone.utc
        )

    def test_metadata_error_is_contained(self):
        adapter = make_bigquery_error_adapter()
        infos = [
            TableInfo(
                schema_name="analytics", table_name="orders",
                table_type="TABLE", columns=[],
            )
        ]
        assert adapter.fetch_last_modified(infos) == {}

    def test_adapter_declares_metadata_support(self):
        assert make_bigquery_adapter().SUPPORTS_METADATA_FRESHNESS is True
