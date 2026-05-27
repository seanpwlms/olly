from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import ibis

from olly.adapters.base import BaseAdapter
from olly.models import UsageRecord

logger = logging.getLogger(__name__)


class PostgresAdapter(BaseAdapter):
    """Postgres warehouse adapter using Ibis for schema introspection and queries.

    Implements the Backend protocol for PostgreSQL, providing schema discovery,
    row counting, timestamp extraction, and content-hashing capabilities.
    """

    SUPPORTS_USAGE_HISTORY = True

    def __init__(self, url: str, **connect_kwargs: Any) -> None:
        """Initialize the adapter and open a Postgres connection via Ibis.

        Args:
            url: A ``postgresql://`` connection URL.
            **connect_kwargs: Extra keyword arguments forwarded to
                ``ibis.postgres.connect()``.
        """
        self._conn = ibis.postgres.connect(url=url, **connect_kwargs)

    def _cast_type(self) -> str:
        return "TEXT"

    def list_schemas(self) -> list[str]:
        """Return the names of all schemas in the connected database."""
        return self._conn.list_schemas()

    def _get_ibis_table(self, schema_name: str, table_name: str) -> Any:
        return self._conn.table(table_name, schema=schema_name)

    def _list_ibis_tables(self, schema_name: str) -> list[str]:
        return self._conn.list_tables(schema=schema_name)

    def fetch_table_usage(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str = "us",
    ) -> list[UsageRecord]:
        """Query pg_stat_user_tables for table access timestamps.

        Requires PostgreSQL 16+ which exposes ``last_seq_scan`` and
        ``last_idx_scan`` timestamp columns. On older versions, logs a
        warning and returns an empty list.

        Args:
            schemas: Schema names to check usage for.
            lookback_days: Tables last accessed more than this many days
                ago are treated as having no recent access.
            region: Ignored (BigQuery compatibility).

        Returns:
            A list of ``UsageRecord`` objects with the last query timestamp
            per table. Tables never scanned have ``last_queried_at=None``.
        """
        if not schemas:
            return []

        schema_filter = ", ".join(
            f"'{s.replace(chr(39), chr(39) * 2)}'" for s in schemas
        )
        sql = (
            "SELECT schemaname, relname, "
            "GREATEST(last_seq_scan, last_idx_scan) AS last_queried_at "
            "FROM pg_stat_user_tables "
            f"WHERE schemaname IN ({schema_filter})"
        )

        try:
            result = self._raw_sql(sql)
            rows = result.fetchall()
        except Exception as exc:
            err_msg = str(exc)
            if "last_seq_scan" in err_msg or "last_idx_scan" in err_msg:
                logger.warning(
                    "Usage check requires PostgreSQL 16+. "
                    "last_seq_scan/last_idx_scan columns not available."
                )
                return []
            raise RuntimeError(
                "Failed to fetch table usage from pg_stat_user_tables"
            ) from exc

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        usage_map: dict[tuple[str, str], datetime | None] = {}
        for schema_name, table_name, last_queried_at in rows:
            ts = last_queried_at
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    ts = None
            usage_map[(str(schema_name), str(table_name))] = ts

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
