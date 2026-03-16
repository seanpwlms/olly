"""Shared test helpers — stubs, factories, and utilities.

Import from here instead of duplicating across test files.
"""

from __future__ import annotations

from contextlib import contextmanager

from olly.models import UsageRecord


# ---------------------------------------------------------------------------
# FakeUsageAdapter — for usage check and CLI unused tests
# ---------------------------------------------------------------------------


class FakeUsageAdapter:
    """Adapter that returns pre-configured usage records.

    Usage:
        adapter = FakeUsageAdapter([UsageRecord("main", "dead", None)])
        findings = check_usage(adapter, ["main"], config)
    """

    def __init__(self, records: list[UsageRecord] | None = None) -> None:
        self._records = records or []

    def list_schemas(self) -> list[str]:
        return ["public"]

    def fetch_table_usage(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str = "us",
    ) -> list[UsageRecord]:
        return self._records


# ---------------------------------------------------------------------------
# Postgres stubs — shared between test_adapters_postgres, test_postgres_usage
# ---------------------------------------------------------------------------


class PostgresStubResult:
    """Minimal stand-in for an Ibis raw_sql result (Postgres)."""

    def __init__(self, rows: list | tuple):
        self._rows = list(rows) if isinstance(rows, list) else [rows]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class PostgresStubConn:
    """Minimal stand-in for an Ibis Postgres connection."""

    def __init__(self, raw_sql_results: list[PostgresStubResult] | None = None):
        self.queries: list[str] = []
        self._results = list(raw_sql_results or [])

    def raw_sql(self, sql: str) -> PostgresStubResult:
        self.queries.append(sql)
        if self._results:
            return self._results.pop(0)
        return PostgresStubResult([])

    def list_tables(self, schema: str | None = None) -> list[str]:
        return []

    def table(self, name: str, schema: str | None = None):
        raise NotImplementedError


def make_postgres_adapter(
    rows: list[tuple] | None = None,
    raw_sql_results: list[PostgresStubResult] | None = None,
):
    """Build a PostgresAdapter with a stub connection (no real DB).

    Two calling conventions:
    - ``make_postgres_adapter(rows=[(4,), (5,)])`` — each tuple becomes one
      fetchone() result from successive raw_sql calls.
    - ``make_postgres_adapter(raw_sql_results=[PostgresStubResult(...)])`` —
      full control over each raw_sql result.
    """
    from olly.adapters.postgres import PostgresAdapter

    adapter = PostgresAdapter.__new__(PostgresAdapter)
    if raw_sql_results is not None:
        adapter._conn = PostgresStubConn(raw_sql_results)
    elif rows is not None:
        # Legacy simple mode: each row becomes a single-row StubResult
        adapter._conn = PostgresStubConn(
            [PostgresStubResult([r]) if isinstance(r, tuple) else PostgresStubResult(r) for r in rows]
        )
    else:
        adapter._conn = PostgresStubConn()
    return adapter


# ---------------------------------------------------------------------------
# Snowflake stubs
# ---------------------------------------------------------------------------


class SnowflakeStubResult:
    def __init__(self, rows):
        self._rows = list(rows)
        self.description = [("col",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class SnowflakeStubConn:
    def __init__(self, rows_per_call=None):
        self._rows_per_call = list(rows_per_call or [])
        self.queries: list[str] = []

    def raw_sql(self, sql):
        self.queries.append(sql)
        rows = self._rows_per_call.pop(0) if self._rows_per_call else []
        return SnowflakeStubResult(rows)


def make_snowflake_adapter(rows_per_call=None, *, use_account_usage=False):
    """Build a SnowflakeAdapter with a stub connection (no real DB)."""
    from olly.adapters.snowflake import SnowflakeAdapter

    adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
    adapter._conn = SnowflakeStubConn(rows_per_call)
    adapter._use_account_usage = use_account_usage
    adapter._default_database = None
    return adapter


def make_snowflake_error_adapter():
    """Build a SnowflakeAdapter whose connection raises on every call."""
    from olly.adapters.snowflake import SnowflakeAdapter

    class _ErrorConn:
        def raw_sql(self, sql):
            raise Exception("connection lost")

    adapter = SnowflakeAdapter.__new__(SnowflakeAdapter)
    adapter._conn = _ErrorConn()
    adapter._use_account_usage = False
    adapter._default_database = None
    return adapter


# ---------------------------------------------------------------------------
# BigQuery adapter factory — lightweight, for tests that just need raw_sql
# ---------------------------------------------------------------------------


class _BigQueryStubRow:
    def __init__(self, vals: tuple):
        self._vals = vals

    def values(self):
        return self._vals


class _BigQueryStubConn:
    def __init__(self, raw_sql_rows: list[list] | None = None):
        self._raw_sql_rows = list(raw_sql_rows or [])
        self.queries: list[str] = []

    def raw_sql(self, sql: str):
        self.queries.append(sql)
        rows = self._raw_sql_rows.pop(0) if self._raw_sql_rows else []
        return [_BigQueryStubRow(tuple(r)) for r in rows]


def make_bigquery_adapter(
    *,
    raw_sql_rows: list[list] | None = None,
    region: str = "us",
):
    """Build a BigQueryAdapter with a stub connection (no real GCP).

    For tests that only exercise raw_sql-based methods (e.g. fetch_query_costs).
    For full BigQuery adapter tests, use the richer stubs in test_adapters_bigquery.py.
    """
    from olly.adapters.bigquery import BigQueryAdapter

    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    adapter._conn = _BigQueryStubConn(raw_sql_rows)
    adapter._use_information_schema_row_counts = True
    adapter._region = region
    return adapter


# ---------------------------------------------------------------------------
# Dashboard test plumbing
# ---------------------------------------------------------------------------


def patch_dashboard(monkeypatch, state_db_path, tmp_path):
    """Wire up monkeypatches for dashboard routes to use a test state DB.

    Returns a FastAPI TestClient ready for API calls.
    """
    from fastapi.testclient import TestClient

    from olly.config import OllyConfig
    from olly.state import StateDB

    test_olly_dir = tmp_path / ".olly"

    monkeypatch.setattr("olly.state.get_olly_dir", lambda: test_olly_dir)
    monkeypatch.setattr("olly.results.get_olly_dir", lambda: test_olly_dir)

    @contextmanager
    def mock_state_db(connection_name: str = "", config=None):
        yield StateDB(db_path=state_db_path), ""

    monkeypatch.setattr("olly.dashboard.api_routes._state_db", mock_state_db)
    monkeypatch.setattr("olly.dashboard.api_routes._get_current_connection", lambda connection_param="", config=None: "test_connection")
    monkeypatch.setattr("olly.dashboard.api_routes._get_all_connections", lambda: ["test_connection"])
    monkeypatch.setattr("olly.dashboard.data.get_all_connections", lambda: ["test_connection"])
    monkeypatch.setattr("olly.dashboard.api_routes.load_config", lambda: OllyConfig())

    from olly.dashboard.app import app
    return TestClient(app)
