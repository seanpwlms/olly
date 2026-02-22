from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import ibis

from olly.adapters.base import BaseAdapter
from olly.models import ColumnInfo, CostRecord, TableInfo, UsageRecord, VolumeRecord

logger = logging.getLogger(__name__)


class BigQueryAdapter(BaseAdapter):
    """Adapter for Google BigQuery warehouses via Ibis.

    Implements the Backend protocol for BigQuery, providing schema
    introspection, row counts, timestamp queries, and content hashing.
    """

    def __init__(
        self,
        project: str,
        *,
        dataset: str | None = None,
        region: str = "us",
        use_information_schema_row_counts: bool = True,
        **connect_kwargs: Any,
    ) -> None:
        """Initialize a BigQuery connection.

        Args:
            project: GCP project ID.
            dataset: Optional default dataset name.
            region: BigQuery region (e.g. ``"us"``, ``"eu"``). Used when
                querying ``INFORMATION_SCHEMA`` views that require a
                region qualifier.
            use_information_schema_row_counts: If True, read row counts from
                INFORMATION_SCHEMA instead of running COUNT(*) queries.
            **connect_kwargs: Extra keyword arguments forwarded to
                ``ibis.bigquery.connect()``.
        """
        self._conn = ibis.bigquery.connect(
            project_id=project,
            dataset_id=dataset,
            **connect_kwargs,
        )
        self._region = region
        self._use_information_schema_row_counts = use_information_schema_row_counts

    # --- BigQuery raw_sql wrapper ---

    def _execute_sql(self, sql: str) -> list[tuple[Any, ...]]:
        """Execute raw SQL and return rows as a list of tuples.

        The Ibis BigQuery backend returns a ``RowIterator`` from
        ``raw_sql()`` which lacks the DBAPI cursor interface. This
        helper normalises the result.
        """
        result = self._conn.raw_sql(sql)
        return [tuple(row.values()) for row in result]

    def _fetch_scalar(self, sql: str, table_label: str) -> int:
        """Override base to use ``_execute_sql``."""
        try:
            rows = self._execute_sql(sql)
            if not rows or rows[0][0] is None:
                return 0
            return int(rows[0][0])
        except Exception as exc:
            raise RuntimeError(f"Failed to run query for {table_label}") from exc

    def _fetch_scalar_str(self, sql: str, table_label: str) -> str | None:
        """Override base to use ``_execute_sql``."""
        try:
            rows = self._execute_sql(sql)
            if not rows or rows[0][0] is None:
                return None
            return str(rows[0][0])
        except Exception as exc:
            raise RuntimeError(f"Failed to run query for {table_label}") from exc

    # --- BigQuery-specific quoting ---

    def _quote_identifier(self, identifier: str) -> str:
        """Wrap an identifier in backticks."""
        return f"`{identifier}`"

    def _format_table(self, schema_name: str, table_name: str) -> str:
        """Return a backtick-quoted ``schema.table`` reference."""
        return f"`{schema_name}.{table_name}`"

    def _build_row_expr(self, columns: list[str]) -> str:
        """Build a CONCAT expression that combines columns into a pipe-delimited string."""
        parts = []
        for idx, col in enumerate(columns):
            quoted = self._quote_identifier(col)
            parts.append(f"COALESCE(CAST({quoted} AS STRING), '')")
            if idx < len(columns) - 1:
                parts.append("'|'")
        return f"CONCAT({', '.join(parts)})"

    # --- Ibis table access ---

    def _get_ibis_table(self, schema_name: str, table_name: str) -> Any:
        return self._conn.table(table_name, database=schema_name)

    def _list_ibis_tables(self, schema_name: str) -> list[str]:
        return self._conn.list_tables(database=schema_name)

    # --- Schema introspection ---

    def list_schemas(self) -> list[str]:
        """Return all dataset names in the connected project."""
        return self._conn.list_databases()

    def fetch_schema_info(self, schemas: list[str]) -> list[TableInfo]:
        """Introspect tables and columns for the given schemas.

        Args:
            schemas: Dataset names to introspect.

        Returns:
            A list of ``TableInfo`` objects with column metadata.
        """
        logger.debug("Fetching schema info for schemas: %s", schemas)
        tables: list[TableInfo] = []
        for schema_name in schemas:
            metadata = self._fetch_table_metadata(schema_name)
            for table_name in self._conn.list_tables(database=schema_name):
                t = self._conn.table(table_name, database=schema_name)
                schema = t.schema()
                table_type = metadata.get(table_name, {}).get("table_type")
                if not isinstance(table_type, str) or not table_type:
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
        return tables

    def _fetch_table_metadata(
        self, schema_name: str
    ) -> dict[str, dict[str, int | str | None]]:
        """Query INFORMATION_SCHEMA for table types and row counts.

        Table types come from ``TABLES``; row counts come from
        ``TABLE_STORAGE`` via a LEFT JOIN so the query works even when
        storage metadata is unavailable.
        """
        try:
            safe_schema = schema_name.replace("`", "")
            safe_region = self._region.replace("`", "")
            rows = self._execute_sql(
                "SELECT t.table_name, t.table_type, s.total_rows "
                f"FROM `{safe_schema}.INFORMATION_SCHEMA.TABLES` t "
                f"LEFT JOIN `region-{safe_region}`.INFORMATION_SCHEMA.TABLE_STORAGE s "
                f"ON t.table_schema = s.table_schema AND t.table_name = s.table_name"
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read table metadata for schema {schema_name}"
            ) from exc

        metadata: dict[str, dict[str, int | str | None]] = {}
        for table_name, table_type, row_count in rows:
            metadata[str(table_name)] = {
                "table_type": str(table_type).upper()
                if table_type is not None
                else None,
                "row_count": row_count,
            }
        return metadata

    def _get_table_type(self, schema_name: str, table_name: str) -> str:
        """Look up whether a table is a TABLE or VIEW via INFORMATION_SCHEMA."""
        try:
            safe_table = table_name.replace("'", "''")
            safe_schema = schema_name.replace("`", "")
            rows = self._execute_sql(
                f"SELECT table_type FROM `{safe_schema}.INFORMATION_SCHEMA.TABLES` "
                f"WHERE table_name = '{safe_table}'"
            )
            row = rows[0] if rows else None
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

    def fetch_row_counts(self, table_infos: list[TableInfo]) -> list[VolumeRecord]:
        """Fetch row counts for the given tables, skipping views.

        Uses INFORMATION_SCHEMA row counts when enabled, otherwise falls
        back to COUNT(*) queries.

        Args:
            table_infos: Tables to count rows for.

        Returns:
            A list of ``VolumeRecord`` objects with row counts.

        Raises:
            RuntimeError: If a row count cannot be determined.
        """
        logger.debug("Fetching row counts for %d tables", len(table_infos))
        records = []
        metadata_by_schema: dict[str, dict[str, dict[str, int | str | None]]] = {}
        for ti in table_infos:
            if ti.table_type == "VIEW":
                continue
            if self._use_information_schema_row_counts:
                metadata = metadata_by_schema.get(ti.schema_name)
                if metadata is None:
                    metadata = self._fetch_table_metadata(ti.schema_name)
                    metadata_by_schema[ti.schema_name] = metadata
                row_count = metadata.get(ti.table_name, {}).get("row_count")
                if row_count is None:
                    raise RuntimeError(
                        "Missing row count for "
                        f"{ti.schema_name}.{ti.table_name} in INFORMATION_SCHEMA"
                    )
                records.append(
                    VolumeRecord(
                        schema_name=ti.schema_name,
                        table_name=ti.table_name,
                        row_count=int(row_count),
                    )
                )
            else:
                try:
                    t = self._conn.table(ti.table_name, database=ti.schema_name)
                    count = t.count().execute()
                    records.append(
                        VolumeRecord(
                            schema_name=ti.schema_name,
                            table_name=ti.table_name,
                            row_count=int(count),
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
            schema_name: BigQuery dataset name.
            table_name: Table to query.
            column: Timestamp column name.

        Raises:
            RuntimeError: If the query fails.
        """
        try:
            t = self._conn.table(table_name, database=schema_name)
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
        """Compute an MD5 content hash over the specified columns.

        Rows are ordered by ``order_by`` before aggregation so the hash
        is deterministic.

        Args:
            schema_name: BigQuery dataset name.
            table_name: Table to hash.
            columns: Columns to include in each row's hash.
            order_by: Column used to order rows before aggregation.
            where_sql: Optional raw SQL WHERE expression.

        Returns:
            Hex-encoded MD5 digest, or None if the table is empty.
        """
        row_expr = self._build_row_expr(columns)
        order_col = self._quote_identifier(order_by)
        table = self._format_table(schema_name, table_name)
        inner = (
            "SELECT TO_HEX(MD5("
            f"{row_expr})) AS row_hash, {order_col} AS order_col FROM {table}"
        )
        if where_sql:
            inner += f" WHERE {where_sql}"
        sql = (
            "SELECT TO_HEX(MD5(STRING_AGG(row_hash, '' ORDER BY order_col))) "
            f"FROM ({inner}) AS rows"
        )
        return self._fetch_scalar_str(sql, f"{schema_name}.{table_name}")

    def fetch_table_usage(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str | None = None,
    ) -> list[UsageRecord]:
        """Query INFORMATION_SCHEMA.JOBS_BY_PROJECT for table access history.

        Args:
            schemas: Dataset names to check usage for.
            lookback_days: How many days of query history to analyze.
            region: BigQuery region for INFORMATION_SCHEMA query.

        Returns:
            A list of ``UsageRecord`` objects with the last query timestamp
            per table. Tables never queried in the lookback window have
            ``last_queried_at=None``.
        """
        if not schemas:
            return []

        effective_region = (region or self._region).replace("`", "")
        schema_filter = ", ".join(
            f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schemas
        )

        sql = (
            "SELECT ref.dataset_id AS schema_name, "
            "ref.table_id AS table_name, "
            "MAX(j.creation_time) AS last_queried_at "
            f"FROM `region-{effective_region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT j, "
            "UNNEST(referenced_tables) AS ref "
            "WHERE j.job_type = 'QUERY' "
            "AND j.state = 'DONE' "
            "AND j.creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), "
            f"INTERVAL {int(lookback_days)} DAY) "
            f"AND ref.dataset_id IN ({schema_filter}) "
            "GROUP BY ref.dataset_id, ref.table_id"
        )

        try:
            rows = self._execute_sql(sql)
        except Exception as exc:
            raise RuntimeError(
                "Failed to fetch table usage from INFORMATION_SCHEMA.JOBS_BY_PROJECT"
            ) from exc

        usage_map: dict[tuple[str, str], datetime] = {}
        for schema_name, table_name, last_queried_at in rows:
            if last_queried_at is not None:
                usage_map[(str(schema_name), str(table_name))] = last_queried_at

        all_tables = self.fetch_schema_info(schemas)
        records = []
        for table in all_tables:
            key = (table.schema_name, table.table_name)
            records.append(
                UsageRecord(
                    schema_name=table.schema_name,
                    table_name=table.table_name,
                    last_queried_at=usage_map.get(key),
                )
            )
        return records

    def fetch_query_costs(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str | None = None,
        price_per_tb_usd: float = 6.25,
    ) -> list[CostRecord]:
        """Query INFORMATION_SCHEMA.JOBS_BY_PROJECT for per-table query costs.

        Args:
            schemas: Dataset names to filter costs for.
            lookback_days: How many days of query history to analyze.
            region: BigQuery region for INFORMATION_SCHEMA query.
            price_per_tb_usd: On-demand price per TB for cost estimation.

        Returns:
            A list of ``CostRecord`` objects with cost data per table/user.
        """
        if not schemas:
            return []

        effective_region = (region or self._region).replace("`", "")
        schema_filter = ", ".join(
            f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schemas
        )
        bytes_per_tb = 1099511627776  # 2^40

        sql = (
            "SELECT ref.dataset_id AS schema_name, "
            "ref.table_id AS table_name, "
            "j.user_email, "
            "SUM(j.total_bytes_billed) AS total_bytes_billed, "
            "COUNT(*) AS query_count "
            f"FROM `region-{effective_region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT j, "
            "UNNEST(referenced_tables) AS ref "
            "WHERE j.job_type = 'QUERY' "
            "AND j.state = 'DONE' "
            "AND j.creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), "
            f"INTERVAL {int(lookback_days)} DAY) "
            f"AND ref.dataset_id IN ({schema_filter}) "
            "GROUP BY ref.dataset_id, ref.table_id, j.user_email"
        )

        try:
            rows = self._execute_sql(sql)
        except Exception as exc:
            raise RuntimeError(
                "Failed to fetch query costs from INFORMATION_SCHEMA.JOBS_BY_PROJECT"
            ) from exc

        records = []
        for schema_name, table_name, user_email, total_bytes, query_count in rows:
            bytes_val = int(total_bytes) if total_bytes else 0
            records.append(
                CostRecord(
                    schema_name=str(schema_name),
                    table_name=str(table_name),
                    user_email=str(user_email),
                    total_bytes_billed=bytes_val,
                    estimated_cost_usd=bytes_val / bytes_per_tb * price_per_tb_usd,
                    query_count=int(query_count),
                )
            )
        return records
