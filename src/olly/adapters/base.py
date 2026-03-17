from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import ibis

from olly.logging import timed_raw_sql
from olly.models import ColumnInfo, CostRecord, TableInfo, UsageRecord, VolumeRecord

if TYPE_CHECKING:
    from olly.adapter import ProgressCallback

logger = logging.getLogger(__name__)


class BaseAdapter:
    """Shared implementation for warehouse adapters.

    Subclasses must set ``_conn`` and may override quoting/formatting methods
    to match their SQL dialect.
    """

    _conn: Any  # Ibis backend connection

    @property
    def backend(self) -> Any:
        """Return the underlying Ibis backend connection."""
        return self._conn

    # --- Identifier quoting (override per dialect) ---

    def _quote_identifier(self, identifier: str) -> str:
        """Wrap an identifier in the dialect's quoting characters."""
        return f'"{identifier}"'

    def _format_table(self, schema_name: str, table_name: str) -> str:
        """Return a fully-qualified, quoted table reference."""
        return f"{self._quote_identifier(schema_name)}.{self._quote_identifier(table_name)}"

    # --- Row expression for hashing (override for BigQuery CONCAT syntax) ---

    def _cast_type(self) -> str:
        """Return the SQL type name used for CAST(... AS <type>)."""
        return "VARCHAR"

    def _build_row_expr(self, columns: list[str]) -> str:
        """Build a SQL expression that concatenates columns for hashing."""
        parts = []
        for col in columns:
            quoted = self._quote_identifier(col)
            parts.append(f"COALESCE(CAST({quoted} AS {self._cast_type()}), '')")
        return " || '|' || ".join(parts)

    # --- Raw SQL execution with query logging ---

    def _raw_sql(self, sql: str) -> Any:
        """Execute raw SQL via Ibis, logging the query and its duration."""
        return timed_raw_sql(self._conn, sql)

    # --- Scalar helpers ---

    def _fetch_scalar(self, sql: str, table_label: str) -> int:
        """Execute *sql* and return the first column of the first row as an int.

        Returns ``0`` when the result is null or empty.
        """
        try:
            result = self._raw_sql(sql)
            row = result.fetchone()
            if not row or row[0] is None:
                return 0
            return int(row[0])
        except Exception as exc:
            raise RuntimeError(f"Failed to run query for {table_label}") from exc

    def _fetch_scalar_str(self, sql: str, table_label: str) -> str | None:
        """Execute *sql* and return the first column of the first row as a string.

        Returns ``None`` when the result is null or empty.
        """
        try:
            result = self._raw_sql(sql)
            row = result.fetchone()
            if not row or row[0] is None:
                return None
            return str(row[0])
        except Exception as exc:
            raise RuntimeError(f"Failed to run query for {table_label}") from exc

    # --- Table type lookup ---

    def _get_table_type(self, schema_name: str, table_name: str) -> str:
        """Return ``'TABLE'`` or ``'VIEW'`` by querying ``information_schema.tables``.

        Subclasses with different SQL dialects (e.g. BigQuery) may override.

        Raises:
            RuntimeError: If the information_schema query fails.
        """
        try:
            safe_schema = schema_name.replace("'", "''")
            safe_table = table_name.replace("'", "''")
            result = self._raw_sql(
                "SELECT table_type FROM information_schema.tables "
                f"WHERE table_schema = '{safe_schema}' AND table_name = '{safe_table}'"
            )
            row = result.fetchone()
            if row:
                val = row[0].upper()
                if "VIEW" in val:
                    return "VIEW"
                return "TABLE"
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read table type for {schema_name}.{table_name}"
            ) from exc
        return "TABLE"

    # --- Ibis table access (override per dialect) ---

    def _get_ibis_table(self, schema_name: str, table_name: str) -> Any:
        """Return an Ibis table expression for the given schema and table.

        Subclasses must override to pass the correct keyword argument
        (``database=`` for DuckDB, ``schema=`` for Postgres, etc.).
        """
        raise NotImplementedError

    def _list_ibis_tables(self, schema_name: str) -> list[str]:
        """Return the table names in a schema via Ibis.

        Subclasses must override to pass the correct keyword argument.
        """
        raise NotImplementedError

    # --- Shared query methods using Ibis ---

    def list_tables(self, schemas: list[str]) -> list[tuple[str, str]]:
        """Return ``(schema_name, table_name)`` pairs across the given schemas."""
        result: list[tuple[str, str]] = []
        for schema_name in schemas:
            for table_name in self._list_ibis_tables(schema_name):
                result.append((schema_name, table_name))
        return result

    def fetch_schema_info(
        self,
        schemas: list[str],
        on_progress: ProgressCallback | None = None,
    ) -> list[TableInfo]:
        """Introspect tables and views across the given schemas."""
        logger.debug("Fetching schema info for schemas: %s", schemas)
        tables: list[TableInfo] = []
        for schema_name in schemas:
            for table_name in self._list_ibis_tables(schema_name):
                t = self._get_ibis_table(schema_name, table_name)
                schema = t.schema()
                table_type = self._get_table_type(schema_name, table_name)
                columns = [
                    ColumnInfo(
                        column_name=col_name,
                        data_type=str(col_type),
                        is_nullable=col_type.nullable,
                    )
                    for col_name, col_type in schema.items()
                ]
                tables.append(
                    TableInfo(
                        schema_name=schema_name,
                        table_name=table_name,
                        table_type=table_type,
                        columns=columns,
                    )
                )
                if on_progress:
                    on_progress(schema_name, table_name)
        return tables

    def fetch_table_schema(self, schema_name: str, table_name: str) -> ibis.Schema:
        """Return the Ibis schema for a table."""
        t = self._get_ibis_table(schema_name, table_name)
        return t.schema()

    def fetch_row_counts(
        self,
        table_infos: list[TableInfo],
        on_progress: ProgressCallback | None = None,
    ) -> list[VolumeRecord]:
        """Fetch row counts for the given tables, skipping views."""
        logger.debug("Fetching row counts for %d tables", len(table_infos))
        records = []
        for ti in table_infos:
            if ti.table_type == "VIEW":
                continue
            try:
                t = self._get_ibis_table(ti.schema_name, ti.table_name)
                count = t.count().execute()
                records.append(
                    VolumeRecord(
                        schema_name=ti.schema_name,
                        table_name=ti.table_name,
                        row_count=int(count),
                    )
                )
                if on_progress:
                    on_progress(ti.schema_name, ti.table_name)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to fetch row count for {ti.schema_name}.{ti.table_name}"
                ) from exc
        return records

    def fetch_max_timestamp(
        self, schema_name: str, table_name: str, column: str
    ) -> datetime | None:
        """Return the maximum value of a timestamp column, or ``None`` if empty."""
        try:
            t = self._get_ibis_table(schema_name, table_name)
            result = t[column].max().execute()
            if result is None:
                return None
            if isinstance(result, datetime):
                return result
            return result.to_pydatetime()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch max timestamp for {schema_name}.{table_name}.{column}"
            ) from exc

    def fetch_hash(
        self,
        schema_name: str,
        table_name: str,
        columns: list[str],
        order_by: str,
        where_sql: str | None,
    ) -> str | None:
        """Compute an MD5 content hash over the specified columns."""
        row_expr = self._build_row_expr(columns)
        order_col = self._quote_identifier(order_by)
        table = self._format_table(schema_name, table_name)
        inner = (
            f"SELECT md5({row_expr}) AS row_hash, {order_col} AS order_col FROM {table}"
        )
        if where_sql:
            inner += f" WHERE {where_sql}"
        sql = (
            "SELECT md5(string_agg(row_hash, '' ORDER BY order_col)) "
            f"FROM ({inner}) AS rows"
        )
        return self._fetch_scalar_str(sql, f"{schema_name}.{table_name}")

    # --- Common query methods ---

    def fetch_count(
        self, schema_name: str, table_name: str, where_sql: str | None
    ) -> int:
        """Return the row count for a table, optionally filtered."""
        sql = f"SELECT COUNT(*) FROM {self._format_table(schema_name, table_name)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        return self._fetch_scalar(sql, f"{schema_name}.{table_name}")

    def fetch_count_distinct(
        self,
        schema_name: str,
        table_name: str,
        column: str,
        where_sql: str | None,
    ) -> int:
        """Return the count of distinct values in a column."""
        col = self._quote_identifier(column)
        sql = (
            "SELECT COUNT(DISTINCT "
            f"{col}) FROM {self._format_table(schema_name, table_name)}"
        )
        if where_sql:
            sql += f" WHERE {where_sql}"
        return self._fetch_scalar(sql, f"{schema_name}.{table_name}")

    def fetch_table_usage(
        self, schemas: list[str], lookback_days: int, region: str = "us"
    ) -> list[UsageRecord]:
        """Not supported by default — returns an empty list."""
        return []

    def fetch_query_costs(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str = "us",
        price_per_tb_usd: float = 6.25,
    ) -> list[CostRecord]:
        """Not supported by default — returns an empty list."""
        return []
