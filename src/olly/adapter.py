from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

import ibis

from olly.config import ConnectionConfig
from olly.models import CostRecord, TableInfo, UsageRecord, VolumeRecord

logger = logging.getLogger(__name__)


class Adapter(Protocol):
    """Protocol that all warehouse adapters must implement."""

    def list_schemas(self) -> list[str]:
        """Return all schema names in the warehouse."""
        ...

    def fetch_schema_info(self, schemas: list[str]) -> list[TableInfo]:
        """Return table/column metadata for the given schemas."""
        ...

    def fetch_row_counts(self, table_infos: list[TableInfo]) -> list[VolumeRecord]:
        """Return current row counts for the given tables."""
        ...

    def fetch_max_timestamp(
        self, schema_name: str, table_name: str, column: str
    ) -> datetime | None:
        """Return the maximum value of a timestamp column, or ``None``."""
        ...

    def fetch_count(
        self, schema_name: str, table_name: str, where_sql: str | None
    ) -> int:
        """Return the row count, optionally filtered by a WHERE clause."""
        ...

    def fetch_count_distinct(
        self, schema_name: str, table_name: str, column: str, where_sql: str | None
    ) -> int:
        """Return the distinct count of a column, optionally filtered."""
        ...

    def fetch_table_schema(self, schema_name: str, table_name: str) -> ibis.Schema:
        """Return the Ibis schema for a table."""
        ...

    def fetch_table_usage(
        self, schemas: list[str], lookback_days: int, region: str = "us"
    ) -> list[UsageRecord]:
        """Return table usage records for the given schemas."""
        ...

    def fetch_query_costs(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str = "us",
        price_per_tb_usd: float = 6.25,
    ) -> list[CostRecord]:
        """Return query cost records for the given schemas."""
        ...

    def fetch_hash(
        self,
        schema_name: str,
        table_name: str,
        columns: list[str],
        order_by: str,
        where_sql: str | None,
    ) -> str | None:
        """Return an aggregate hash over the specified columns, or ``None``."""
        ...


def connect_typed(conn: ConnectionConfig) -> Adapter:
    """Create a warehouse adapter from a typed :class:`ConnectionConfig`.

    Args:
        conn: Typed connection configuration.

    Returns:
        An ``Adapter`` instance connected to the specified warehouse.

    Raises:
        ValueError: If the connection type is not recognized.
    """
    logger.debug("Connecting via %s adapter", conn.type)
    if conn.type == "duckdb":
        from olly.adapters.duckdb import DuckDBAdapter

        return DuckDBAdapter(conn.path, **conn.extras)
    if conn.type == "postgres":
        from olly.adapters.postgres import PostgresAdapter

        if conn.url is None:
            raise ValueError("Postgres connection requires 'url'")
        return PostgresAdapter(conn.url, **conn.extras)
    if conn.type == "bigquery":
        from olly.adapters.bigquery import BigQueryAdapter

        if conn.project is None:
            raise ValueError("BigQuery connection requires 'project'")
        return BigQueryAdapter(
            conn.project,
            dataset=conn.dataset,
            region=conn.region or "us",
            use_information_schema_row_counts=conn.use_information_schema_row_counts,
            **conn.extras,
        )
    if conn.type == "snowflake":
        from olly.adapters.snowflake import SnowflakeAdapter

        if conn.account is None:
            raise ValueError("Snowflake connection requires 'account'")
        return SnowflakeAdapter(
            conn.account,
            database=conn.database,
            use_account_usage=conn.use_account_usage,
            **conn.extras,
        )
    raise ValueError(f"Unsupported connection type: {conn.type}")


def connect_connection_string(connection_string: str) -> Adapter:
    """Create a warehouse adapter from a raw connection string.

    Used by integrity checks which operate on raw source/target connection
    strings. Parses the URL prefix to determine the adapter type and
    extracts typed fields from the URL.

    Args:
        connection_string: A prefixed connection string.

    Returns:
        An ``Adapter`` instance connected to the specified warehouse.

    Raises:
        ValueError: If the connection string prefix is not recognized.
    """
    from olly.config import _parse_legacy_connection_string

    conn = _parse_legacy_connection_string(connection_string)
    return connect_typed(conn)
