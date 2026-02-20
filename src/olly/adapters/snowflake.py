from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import ibis

from olly.adapters.base import BaseAdapter
from olly.models import ColumnInfo, TableInfo, VolumeRecord

logger = logging.getLogger(__name__)


class SnowflakeAdapter(BaseAdapter):
    """Adapter for Snowflake warehouses via Ibis.

    Implements the Adapter protocol for Snowflake's 3-level hierarchy
    (database > schema > table). Schema names use dotted notation
    ``"database.schema"`` throughout the public interface.
    """

    def __init__(
        self,
        account: str,
        *,
        database: str | None = None,
        use_account_usage: bool = False,
        **connect_kwargs: Any,
    ) -> None:
        """Initialize a Snowflake connection.

        Args:
            account: Snowflake account identifier.
            database: Optional default database name.
            use_account_usage: If True, use ``SNOWFLAKE.ACCOUNT_USAGE``
                views instead of per-database ``INFORMATION_SCHEMA``.
            **connect_kwargs: Extra keyword arguments forwarded to
                ``ibis.snowflake.connect()``.
        """
        self._default_database = database
        self._use_account_usage = use_account_usage
        self._conn = ibis.snowflake.connect(
            account=account,
            database=self._default_database,
            **connect_kwargs,
        )

    def _get_ibis_table(self, schema_name: str, table_name: str) -> Any:
        database, schema = _split_schema(schema_name)
        return self._conn.table(table_name, database=database, schema=schema)

    def _list_ibis_tables(self, schema_name: str) -> list[str]:
        database, schema = _split_schema(schema_name)
        return self._conn.list_tables(database=database, schema=schema)

    def list_schemas(self) -> list[str]:
        """Return all ``"database.schema"`` pairs visible to the connection.

        When ``use_account_usage`` is enabled, queries
        ``SNOWFLAKE.ACCOUNT_USAGE.SCHEMATA``. Otherwise queries each
        database's ``INFORMATION_SCHEMA.SCHEMATA``.
        """
        if self._use_account_usage:
            result = self._conn.raw_sql(
                "SELECT CATALOG_NAME, SCHEMA_NAME "
                "FROM SNOWFLAKE.ACCOUNT_USAGE.SCHEMATA "
                "WHERE DELETED IS NULL"
            )
            rows = result.fetchall()
            return [f"{row[0]}.{row[1]}" for row in rows]

        result = self._conn.raw_sql("SHOW DATABASES")
        databases = [row[1] for row in result.fetchall()]
        schemas: list[str] = []
        for db in databases:
            try:
                result = self._conn.raw_sql(
                    f'SELECT SCHEMA_NAME FROM "{db}".INFORMATION_SCHEMA.SCHEMATA'
                )
                for row in result.fetchall():
                    schemas.append(f"{db}.{row[0]}")
            except Exception:
                logger.debug("Skipping database %s (no access)", db)
        return schemas

    def fetch_schema_info(self, schemas: list[str]) -> list[TableInfo]:
        """Introspect tables and columns for the given schemas.

        Args:
            schemas: Schema names as ``"database.schema"`` strings.

        Returns:
            A list of ``TableInfo`` objects with column metadata.
        """
        logger.debug("Fetching schema info for schemas: %s", schemas)
        tables: list[TableInfo] = []
        by_db: dict[str, list[str]] = {}
        for schema_name in schemas:
            database, schema = _split_schema(schema_name)
            by_db.setdefault(database, []).append(schema)

        for database, schema_list in by_db.items():
            metadata = self._fetch_table_metadata(database, schema_list)
            columns_data = self._fetch_columns(database, schema_list)

            for (db, sch, tbl), col_list in columns_data.items():
                dotted = f"{db}.{sch}"
                table_type = metadata.get((db, sch, tbl), "TABLE")
                tables.append(
                    TableInfo(
                        schema_name=dotted,
                        table_name=tbl,
                        table_type=table_type,
                        columns=col_list,
                    )
                )
        return tables

    def _fetch_table_metadata(
        self, database: str, schema_list: list[str]
    ) -> dict[tuple[str, str, str], str]:
        """Query INFORMATION_SCHEMA.TABLES or ACCOUNT_USAGE.TABLES for table types."""
        metadata: dict[tuple[str, str, str], str] = {}
        schema_filter = ", ".join(
            f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schema_list
        )

        safe_db = database.replace("'", "''")
        safe_db_ident = database.replace('"', '""')
        if self._use_account_usage:
            result = self._conn.raw_sql(
                "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                "FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES "
                f"WHERE TABLE_CATALOG = '{safe_db}' "
                f"AND TABLE_SCHEMA IN ({schema_filter}) "
                "AND DELETED IS NULL"
            )
        else:
            result = self._conn.raw_sql(
                "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                f'FROM "{safe_db_ident}".INFORMATION_SCHEMA.TABLES '
                f"WHERE TABLE_SCHEMA IN ({schema_filter})"
            )

        for row in result.fetchall():
            cat, sch, tbl, ttype = row[0], row[1], row[2], row[3]
            val = str(ttype).upper() if ttype else "TABLE"
            if "VIEW" in val:
                val = "VIEW"
            else:
                val = "TABLE"
            metadata[(str(cat), str(sch), str(tbl))] = val
        return metadata

    def _fetch_columns(
        self, database: str, schema_list: list[str]
    ) -> dict[tuple[str, str, str], list[ColumnInfo]]:
        """Query INFORMATION_SCHEMA.COLUMNS or ACCOUNT_USAGE.COLUMNS."""
        columns: dict[tuple[str, str, str], list[ColumnInfo]] = {}
        schema_filter = ", ".join(
            f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schema_list
        )
        safe_db = database.replace("'", "''")
        safe_db_ident = database.replace('"', '""')

        if self._use_account_usage:
            result = self._conn.raw_sql(
                "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, "
                "COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                "FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS "
                f"WHERE TABLE_CATALOG = '{safe_db}' "
                f"AND TABLE_SCHEMA IN ({schema_filter}) "
                "AND DELETED IS NULL "
                "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
            )
        else:
            result = self._conn.raw_sql(
                "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, "
                "COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                f'FROM "{safe_db_ident}".INFORMATION_SCHEMA.COLUMNS '
                f"WHERE TABLE_SCHEMA IN ({schema_filter}) "
                "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
            )

        for row in result.fetchall():
            cat, sch, tbl = str(row[0]), str(row[1]), str(row[2])
            key = (cat, sch, tbl)
            col = ColumnInfo(
                column_name=str(row[3]),
                data_type=str(row[4]),
                is_nullable=str(row[5]).upper() == "YES",
            )
            columns.setdefault(key, []).append(col)
        return columns

    def fetch_row_counts(self, table_infos: list[TableInfo]) -> list[VolumeRecord]:
        """Fetch row counts for the given tables, skipping views.

        When ``use_account_usage`` is enabled, reads counts from
        ``SNOWFLAKE.ACCOUNT_USAGE.TABLES``. Otherwise runs ``COUNT(*)``
        queries per table.

        Args:
            table_infos: Tables to count rows for.

        Returns:
            A list of ``VolumeRecord`` objects with row counts.
        """
        logger.debug("Fetching row counts for %d tables", len(table_infos))
        records: list[VolumeRecord] = []

        if self._use_account_usage:
            by_db: dict[str, list[TableInfo]] = {}
            for ti in table_infos:
                if ti.table_type == "VIEW":
                    continue
                database, _ = _split_schema(ti.schema_name)
                by_db.setdefault(database, []).append(ti)

            for database, infos in by_db.items():
                schema_list = list({_split_schema(ti.schema_name)[1] for ti in infos})
                schema_filter = ", ".join(
                    f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schema_list
                )
                safe_db = database.replace("'", "''")
                result = self._conn.raw_sql(
                    "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, ROW_COUNT "
                    "FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES "
                    f"WHERE TABLE_CATALOG = '{safe_db}' "
                    f"AND TABLE_SCHEMA IN ({schema_filter}) "
                    "AND DELETED IS NULL"
                )
                count_map: dict[tuple[str, str, str], int] = {}
                for row in result.fetchall():
                    count_map[(str(row[0]), str(row[1]), str(row[2]))] = (
                        int(row[3]) if row[3] is not None else 0
                    )

                for ti in infos:
                    db, sch = _split_schema(ti.schema_name)
                    row_count = count_map.get((db, sch, ti.table_name), 0)
                    records.append(
                        VolumeRecord(
                            schema_name=ti.schema_name,
                            table_name=ti.table_name,
                            row_count=row_count,
                        )
                    )
        else:
            for ti in table_infos:
                if ti.table_type == "VIEW":
                    continue
                try:
                    table = self._format_table(ti.schema_name, ti.table_name)
                    sql = f"SELECT COUNT(*) FROM {table}"
                    result = self._conn.raw_sql(sql)
                    row = result.fetchone()
                    count = int(row[0]) if row and row[0] is not None else 0
                    records.append(
                        VolumeRecord(
                            schema_name=ti.schema_name,
                            table_name=ti.table_name,
                            row_count=count,
                        )
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to fetch row count for {ti.schema_name}.{ti.table_name}"
                    ) from exc
        return records

    def fetch_max_timestamp(
        self, schema_name: str, table_name: str, column: str
    ) -> datetime | None:
        """Return the maximum value of a timestamp column, or None if empty.

        Args:
            schema_name: Schema as ``"database.schema"``.
            table_name: Table to query.
            column: Timestamp column name.

        Raises:
            RuntimeError: If the query fails.
        """
        col = self._quote_identifier(column)
        table = self._format_table(schema_name, table_name)
        sql = f"SELECT MAX({col}) FROM {table}"
        try:
            result = self._conn.raw_sql(sql)
            row = result.fetchone()
            if not row or row[0] is None:
                return None
            val = row[0]
            if isinstance(val, datetime):
                return val
            return val.to_pydatetime()
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
        """Compute an MD5 content hash over the specified columns.

        Uses Snowflake's ``MD5()`` and ``LISTAGG()`` for aggregation.

        Args:
            schema_name: Schema as ``"database.schema"``.
            table_name: Table to hash.
            columns: Columns to include in each row's hash.
            order_by: Column to order rows by before aggregation.
            where_sql: Optional raw SQL WHERE expression.

        Returns:
            Hex-encoded MD5 digest, or None if the table is empty.
        """
        row_expr = self._build_row_expr(columns)
        order_col = self._quote_identifier(order_by)
        table = self._format_table(schema_name, table_name)
        inner = (
            f"SELECT MD5({row_expr}) AS row_hash, {order_col} AS order_col FROM {table}"
        )
        if where_sql:
            inner += f" WHERE {where_sql}"
        sql = (
            "SELECT MD5(LISTAGG(row_hash, '') WITHIN GROUP (ORDER BY order_col)) "
            f"FROM ({inner})"
        )
        return self._fetch_scalar_str(sql, f"{schema_name}.{table_name}")

    def _format_table(self, schema_name: str, table_name: str) -> str:
        """Return a 3-part quoted ``"database"."schema"."table"`` reference."""
        database, schema = _split_schema(schema_name)
        return (
            f"{self._quote_identifier(database)}."
            f"{self._quote_identifier(schema)}."
            f"{self._quote_identifier(table_name)}"
        )


def _split_schema(schema_name: str) -> tuple[str, str]:
    """Parse a ``"database.schema"`` string into its two parts.

    Args:
        schema_name: Dotted ``"database.schema"`` identifier.

    Returns:
        A ``(database, schema)`` tuple.

    Raises:
        ValueError: If the string does not contain exactly one dot.
    """
    parts = schema_name.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Expected 'database.schema' format, got: {schema_name!r}")
    return parts[0], parts[1]
