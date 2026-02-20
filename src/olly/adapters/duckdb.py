from __future__ import annotations

import logging
from typing import Any

import ibis

from olly.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class DuckDBAdapter(BaseAdapter):
    """Adapter for DuckDB warehouses using Ibis for query execution.

    Implements the Backend protocol, providing schema introspection,
    row counts, timestamp queries, and content hashing via DuckDB.
    """

    def __init__(self, path: str | None = None, **connect_kwargs: Any) -> None:
        """Initialize a DuckDB connection.

        Args:
            path: Path to the DuckDB file, or ``None`` for in-memory.
            **connect_kwargs: Extra keyword arguments forwarded to
                ``ibis.duckdb.connect()``.
        """
        self._conn = ibis.duckdb.connect(path if path else ":memory:", **connect_kwargs)

    def list_schemas(self) -> list[str]:
        """Return the names of all schemas in the connected database."""
        return self._conn.list_databases()

    def _get_ibis_table(self, schema_name: str, table_name: str) -> Any:
        return self._conn.table(table_name, database=schema_name)

    def _list_ibis_tables(self, schema_name: str) -> list[str]:
        return self._conn.list_tables(database=schema_name)
