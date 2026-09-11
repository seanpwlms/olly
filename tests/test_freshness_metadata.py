"""Tests for metadata-based freshness detection and strategy resolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from olly.adapter import Adapter
from olly.checks.freshness import _resolve_strategy, check_freshness
from olly.config import ResolvedTableSettings, Settings
from olly.models import Finding, TableInfo
from olly.state import BaseStateStore


def make_settings(
    *,
    freshness_column: str | None = None,
    freshness_method: str = "auto",
    freshness_threshold_hours: float = 24.0,
) -> ResolvedTableSettings:
    """Build a ResolvedTableSettings with test-friendly defaults."""
    return ResolvedTableSettings(
        freshness_column=freshness_column,
        freshness_method=freshness_method,
        freshness_threshold_hours=freshness_threshold_hours,
        volume_zscore_threshold=3.0,
        volume_method="ewma",
        freshness_column_source="global",
        freshness_method_source="global",
        freshness_threshold_hours_source="global",
        volume_zscore_threshold_source="global",
        volume_method_source="global",
    )


def make_table(name: str = "orders", table_type: str = "TABLE") -> TableInfo:
    return TableInfo(
        schema_name="main", table_name=name, table_type=table_type, columns=[]
    )


class FakeAdapter:
    """Adapter stub that records which access path the check used."""

    def __init__(
        self,
        *,
        supports_metadata: bool = True,
        last_modified: dict | None = None,
        max_timestamp: datetime | None = None,
        raise_on_metadata: bool = False,
    ) -> None:
        self.SUPPORTS_METADATA_FRESHNESS = supports_metadata
        self._last_modified = last_modified or {}
        self._max_timestamp = max_timestamp
        self._raise_on_metadata = raise_on_metadata
        self.last_modified_calls: list[list[TableInfo]] = []
        self.max_timestamp_calls: list[tuple[str, str, str]] = []

    def fetch_last_modified(self, table_infos):
        self.last_modified_calls.append(list(table_infos))
        if self._raise_on_metadata:
            raise RuntimeError("catalog unavailable")
        return self._last_modified

    def fetch_max_timestamp(self, schema_name, table_name, column):
        self.max_timestamp_calls.append((schema_name, table_name, column))
        return self._max_timestamp


class FakeState:
    """State store stub returning a fixed unchanged-snapshot count."""

    def __init__(self, unchanged: int = 0) -> None:
        self._unchanged = unchanged

    def get_recent_volume_unchanged_count(self, schema, table, depth, connection_name=""):
        return self._unchanged


def run_check(
    backend: FakeAdapter,
    tables: list[TableInfo],
    settings: Settings,
    overrides: dict,
    state: FakeState,
    connection_name: str = "",
) -> list[Finding]:
    """Call check_freshness with the stubs cast to their real interfaces."""
    return check_freshness(
        cast("Adapter", backend),
        tables,
        settings,
        overrides,
        cast("BaseStateStore", state),
        connection_name,
    )


def resolve(
    backend: FakeAdapter,
    settings: Settings,
    override: ResolvedTableSettings | None,
) -> str:
    """Call _resolve_strategy with the adapter stub cast to Adapter."""
    return _resolve_strategy(cast("Adapter", backend), settings, override)


# --- Strategy resolution ---


@pytest.mark.parametrize(
    "method,has_column,supports_metadata,expected",
    [
        # auto: an explicit column wins, else metadata, else proxy
        ("auto", True, True, "column"),
        ("auto", False, True, "metadata"),
        ("auto", True, False, "column"),
        ("auto", False, False, "proxy"),
        # metadata: never scans, falls back to proxy when unsupported
        ("metadata", True, True, "metadata"),
        ("metadata", False, True, "metadata"),
        ("metadata", True, False, "proxy"),
        ("metadata", False, False, "proxy"),
        # column: requires a configured column
        ("column", True, True, "column"),
        ("column", False, True, "proxy"),
    ],
)
def test_resolve_strategy(method, has_column, supports_metadata, expected):
    backend = FakeAdapter(supports_metadata=supports_metadata)
    override = make_settings(
        freshness_method=method,
        freshness_column="updated_at" if has_column else None,
    )
    assert resolve(backend, Settings(), override) == expected


def test_resolve_strategy_falls_back_to_global_settings():
    """With no per-table override, the global freshness_method applies."""
    backend = FakeAdapter(supports_metadata=True)
    assert resolve(backend, Settings(freshness_method="metadata"), None) == (
        "metadata"
    )
    assert resolve(
        FakeAdapter(supports_metadata=False), Settings(), None
    ) == "proxy"


# --- Metadata path ---


def test_metadata_stale_produces_finding():
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(
        last_modified={("main", "orders"): now - timedelta(hours=50)}
    )
    findings = run_check(
        backend, [make_table()], Settings(), {}, FakeState()
    )
    assert len(findings) == 1
    assert findings[0].details["method"] == "metadata"
    assert findings[0].details["source"] == "catalog_last_modified"
    assert findings[0].details["age_hours"] == pytest.approx(50, abs=0.2)
    # error, not warning, because age exceeds 2x the threshold
    assert findings[0].severity == "error"
    assert backend.max_timestamp_calls == []


def test_metadata_fresh_produces_no_finding():
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(last_modified={("main", "orders"): now - timedelta(hours=1)})
    findings = run_check(
        backend, [make_table()], Settings(), {}, FakeState()
    )
    assert findings == []
    assert backend.max_timestamp_calls == []


def test_metadata_is_batched_into_one_call():
    """All metadata tables resolve from a single adapter call, not one per table."""
    now = datetime.now(timezone.utc)
    tables = [make_table(f"t{i}") for i in range(25)]
    backend = FakeAdapter(
        last_modified={
            ("main", t.table_name): now - timedelta(hours=50) for t in tables
        }
    )
    findings = run_check(backend, tables, Settings(), {}, FakeState())
    assert len(findings) == 25
    assert len(backend.last_modified_calls) == 1
    assert len(backend.last_modified_calls[0]) == 25


def test_views_are_excluded_from_metadata_fetch():
    backend = FakeAdapter(last_modified={})
    tables = [make_table("orders"), make_table("orders_view", table_type="VIEW")]
    run_check(backend, tables, Settings(), {}, FakeState())
    assert [t.table_name for t in backend.last_modified_calls[0]] == ["orders"]


def test_missing_metadata_falls_back_to_proxy():
    """A table absent from the catalog response uses the staleness proxy."""
    backend = FakeAdapter(last_modified={})
    findings = run_check(
        backend, [make_table()], Settings(), {}, FakeState(unchanged=5)
    )
    assert len(findings) == 1
    assert findings[0].details["method"] == "proxy"
    assert backend.max_timestamp_calls == []


def test_metadata_fetch_failure_falls_back_to_proxy():
    """An adapter error is contained -- the run continues via the proxy."""
    backend = FakeAdapter(raise_on_metadata=True)
    findings = run_check(
        backend, [make_table()], Settings(), {}, FakeState(unchanged=5)
    )
    assert len(findings) == 1
    assert findings[0].details["method"] == "proxy"


def test_naive_metadata_timestamp_treated_as_utc():
    backend = FakeAdapter(
        last_modified={("main", "orders"): datetime(2000, 1, 1)}  # naive
    )
    findings = run_check(backend, [make_table()], Settings(), {}, FakeState())
    assert len(findings) == 1
    assert findings[0].details["last_modified_at"].endswith("+00:00")


# --- Column path preserved ---


def test_column_method_still_scans():
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(max_timestamp=now - timedelta(hours=50))
    overrides = {
        ("main", "orders"): make_settings(
            freshness_column="updated_at", freshness_method="column"
        )
    }
    findings = run_check(
        backend, [make_table()], Settings(), overrides, FakeState()
    )
    assert len(findings) == 1
    assert findings[0].details["method"] == "column"
    assert findings[0].details["column"] == "updated_at"
    assert backend.max_timestamp_calls == [("main", "orders", "updated_at")]
    # the metadata path was never consulted for this table
    assert backend.last_modified_calls == []


def test_metadata_method_never_scans_even_with_column_set():
    """freshness_method='metadata' is the hard opt-out from table scans."""
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(
        last_modified={("main", "orders"): now - timedelta(hours=50)},
        max_timestamp=now,
    )
    overrides = {
        ("main", "orders"): make_settings(
            freshness_column="updated_at", freshness_method="metadata"
        )
    }
    findings = run_check(
        backend, [make_table()], Settings(), overrides, FakeState()
    )
    assert len(findings) == 1
    assert findings[0].details["method"] == "metadata"
    assert backend.max_timestamp_calls == []


def test_column_unreadable_reports_failure():
    backend = FakeAdapter(max_timestamp=None)
    overrides = {
        ("main", "orders"): make_settings(
            freshness_column="updated_at", freshness_method="column"
        )
    }
    findings = run_check(
        backend, [make_table()], Settings(), overrides, FakeState()
    )
    assert len(findings) == 1
    assert findings[0].details["reason"] == "null_or_unreadable"
    assert findings[0].details["method"] == "column"


def test_mixed_strategies_in_one_run():
    """Column, metadata, and proxy tables coexist in a single check."""
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(
        last_modified={("main", "meta_tbl"): now - timedelta(hours=50)},
        max_timestamp=now - timedelta(hours=50),
    )
    tables = [make_table("col_tbl"), make_table("meta_tbl"), make_table("proxy_tbl")]
    overrides = {
        ("main", "col_tbl"): make_settings(freshness_column="updated_at"),
        ("main", "proxy_tbl"): make_settings(freshness_method="column"),  # no column
    }
    findings = run_check(
        backend, tables, Settings(), overrides, FakeState(unchanged=5)
    )
    by_table = {f.table_name: f.details["method"] for f in findings}
    assert by_table == {
        "col_tbl": "column",
        "meta_tbl": "metadata",
        "proxy_tbl": "proxy",
    }
    # only the one metadata-strategy table was sent to the catalog
    assert [t.table_name for t in backend.last_modified_calls[0]] == ["meta_tbl"]


def test_all_findings_are_freshness_type():
    now = datetime.now(timezone.utc)
    backend = FakeAdapter(last_modified={("main", "orders"): now - timedelta(hours=30)})
    findings = run_check(backend, [make_table()], Settings(), {}, FakeState())
    assert all(isinstance(f, Finding) for f in findings)
    assert all(f.check_type == "freshness" for f in findings)
    assert findings[0].severity == "warning"  # between 1x and 2x threshold


# --- Adapter capability declaration ---


def test_duckdb_and_postgres_decline_metadata_freshness():
    """Warehouses with no reliable catalog last-modified must not claim support."""
    from olly.adapters.base import BaseAdapter
    from olly.adapters.duckdb import DuckDBAdapter
    from olly.adapters.postgres import PostgresAdapter

    assert BaseAdapter.SUPPORTS_METADATA_FRESHNESS is False
    assert DuckDBAdapter.SUPPORTS_METADATA_FRESHNESS is False
    assert PostgresAdapter.SUPPORTS_METADATA_FRESHNESS is False


def test_base_adapter_returns_empty_last_modified():
    from olly.adapters.base import BaseAdapter

    adapter = BaseAdapter.__new__(BaseAdapter)
    assert adapter.fetch_last_modified([make_table()]) == {}


def test_coerce_datetime_handles_unparseable_values():
    from olly.adapters.base import coerce_datetime

    assert coerce_datetime(None) is None
    assert coerce_datetime("not-a-date") is None
    assert coerce_datetime(12345) is None
    assert coerce_datetime(datetime(2026, 1, 1, tzinfo=timezone.utc)) == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
