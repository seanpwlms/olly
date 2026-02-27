"""Warehouse-backed state store implementation."""

from __future__ import annotations

import logging
from typing import Any

from olly.state.base import BaseStateStore

logger = logging.getLogger(__name__)

# Per-dialect SQL type mappings and quoting
_DIALECTS: dict[str, dict[str, Any]] = {
    "duckdb": {
        "text": "VARCHAR",
        "integer": "INTEGER",
        "real": "DOUBLE",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": True,
    },
    "postgres": {
        "text": "TEXT",
        "integer": "INTEGER",
        "real": "DOUBLE PRECISION",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": True,
    },
    "snowflake": {
        "text": "VARCHAR",
        "integer": "INTEGER",
        "real": "DOUBLE",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": False,
    },
    "bigquery": {
        "text": "STRING",
        "integer": "INT64",
        "real": "FLOAT64",
        "boolean": "BOOL",
        "quote": lambda s: f"`{s}`",
        "indexes": False,
    },
}


def _escape(value: str) -> str:
    """Escape a string value for SQL literal inclusion."""
    return value.replace("'", "''")


class WarehouseStateStore(BaseStateStore):
    """State store backed by tables in the connected data warehouse.

    Note: Concurrent snapshots against the same warehouse state schema are
    not supported. The ``_next_id()`` approach (MAX(id) + 1) is not safe
    for concurrent access.
    """

    def __init__(self, conn: Any, schema: str, conn_type: str) -> None:
        self._conn = conn
        self._schema = schema
        dialect = _DIALECTS.get(conn_type, _DIALECTS["postgres"])
        self._quote = dialect["quote"]
        self._text = dialect["text"]
        self._integer = dialect["integer"]
        self._real = dialect["real"]
        self._boolean = dialect["boolean"]
        self._indexes = dialect["indexes"]
        self._init_tables()

    def _table(self, name: str) -> str:
        return f"{self._quote(self._schema)}.{self._quote(name)}"

    def _exec(self, sql: str) -> Any:
        return self._conn.raw_sql(sql)

    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        resolved = self._resolve_params(sql, params)
        result = self._exec(resolved)
        return result.fetchall()

    def _execute(self, sql: str, params: dict[str, Any] | None = None) -> int | None:
        resolved = self._resolve_params(sql, params)
        self._exec(resolved)
        # Warehouse doesn't support lastrowid; use _next_id for snapshots
        return None

    def _execute_many(
        self, sql: str, column_names: list[str], rows: list[tuple]
    ) -> None:
        if not rows:
            return
        # Build a multi-row VALUES insert
        # Extract the table and column part from the SQL template
        # e.g., "INSERT INTO schema.table (col1, col2) VALUES (:col1, :col2)"
        values_idx = sql.upper().index("VALUES")
        prefix = sql[:values_idx]

        all_values = []
        for row in rows:
            parts = []
            for val in row:
                if isinstance(val, str):
                    parts.append(f"'{_escape(val)}'")
                elif isinstance(val, bool):
                    parts.append("1" if val else "0")
                elif val is None:
                    parts.append("NULL")
                else:
                    parts.append(str(val))
            all_values.append(f"({', '.join(parts)})")

        self._exec(f"{prefix}VALUES {', '.join(all_values)}")

    def _resolve_params(self, sql: str, params: dict[str, Any] | None) -> str:
        """Replace :name placeholders with escaped literal values."""
        if params is None:
            return sql
        import re
        def replacer(m: re.Match) -> str:
            name = m.group(1)
            val = params[name]
            if isinstance(val, str):
                return f"'{_escape(val)}'"
            if isinstance(val, bool):
                return "1" if val else "0"
            if val is None:
                return "NULL"
            return str(val)
        return re.sub(r":([a-zA-Z_]\w*)", replacer, sql)

    def _delete_by_ids(self, table: str, column: str, ids: list[int]) -> None:
        id_list = ", ".join(str(i) for i in ids)
        self._exec(
            f"DELETE FROM {self._table(table)} WHERE {column} IN ({id_list})"
        )

    # Override create_snapshot to use _next_id since warehouse has no AUTOINCREMENT
    def _next_id(self, table: str = "snapshots") -> int:
        """Get next ID for a table. Not safe for concurrent access."""
        row = self._query_one(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {self._table(table)}"
        )
        return row[0] if row else 1

    def create_snapshot(self, connection_name: str = "") -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._next_id("snapshots")
        self._exec(
            f"INSERT INTO {self._table('snapshots')} (id, created_at, connection_name) "
            f"VALUES ({new_id}, '{_escape(now)}', '{_escape(connection_name)}')"
        )
        logger.debug("Created warehouse snapshot #%d", new_id)
        return new_id

    def store_findings(self, findings: list) -> None:
        """Override to include auto-generated IDs for warehouse."""
        if not findings:
            return
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        finding_id = self._next_id("findings")
        values = []
        for f in findings:
            details_json = json.dumps(f.details).replace("'", "''")
            values.append(
                f"({finding_id}, '{_escape(now)}', '{_escape(f.connection_name)}', "
                f"'{_escape(f.check_type)}', '{_escape(f.severity)}', "
                f"'{_escape(f.schema_name)}', '{_escape(f.table_name)}', "
                f"'{_escape(f.description)}', '{details_json}')"
            )
            finding_id += 1
        self._exec(
            f"INSERT INTO {self._table('findings')} "
            f"(id, created_at, connection_name, check_type, severity, schema_name, "
            f"table_name, description, details) "
            f"VALUES {', '.join(values)}"
        )
        logger.debug("Stored %d findings to warehouse", len(findings))

    def store_dbt_findings(self, dbt_findings: list) -> None:
        """Override to include auto-generated IDs for warehouse."""
        if not dbt_findings:
            return
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        finding_id = self._next_id("dbt_findings")
        values = []
        for f in dbt_findings:
            details_json = json.dumps(f.details).replace("'", "''")
            values.append(
                f"({finding_id}, '{_escape(now)}', '{_escape(f.resource_type)}', "
                f"'{_escape(f.severity)}', '{_escape(f.unique_id)}', "
                f"'{_escape(f.status)}', {f.execution_time}, "
                f"'{_escape(f.description)}', '{details_json}')"
            )
            finding_id += 1
        self._exec(
            f"INSERT INTO {self._table('dbt_findings')} "
            f"(id, created_at, resource_type, severity, unique_id, status, "
            f"execution_time, description, details) "
            f"VALUES {', '.join(values)}"
        )
        logger.debug("Stored %d dbt findings to warehouse", len(dbt_findings))

    def _init_tables(self) -> None:
        schema_q = self._quote(self._schema)
        self._exec(f"CREATE SCHEMA IF NOT EXISTS {schema_q}")

        t = self._text
        i = self._integer
        r = self._real
        b = self._boolean
        snapshots = self._table("snapshots")
        schema_snap = self._table("schema_snapshot")
        volume_snap = self._table("volume_snapshot")
        cost_runs = self._table("cost_runs")
        cost_records = self._table("cost_records")

        self._exec(
            f"CREATE TABLE IF NOT EXISTS {snapshots} ("
            f"id {i} NOT NULL, "
            f"created_at {t} NOT NULL, "
            f"connection_name {t} NOT NULL)"
        )
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {schema_snap} ("
            f"snapshot_id {i} NOT NULL, "
            f"schema_name {t} NOT NULL, "
            f"table_name {t} NOT NULL, "
            f"table_type {t} NOT NULL, "
            f"column_name {t} NOT NULL, "
            f"data_type {t} NOT NULL, "
            f"is_nullable {b} NOT NULL)"
        )
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {volume_snap} ("
            f"snapshot_id {i} NOT NULL, "
            f"schema_name {t} NOT NULL, "
            f"table_name {t} NOT NULL, "
            f"row_count {i} NOT NULL)"
        )
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {cost_runs} ("
            f"id {i} NOT NULL, "
            f"created_at {t} NOT NULL, "
            f"connection_name {t} NOT NULL)"
        )
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {cost_records} ("
            f"cost_run_id {i} NOT NULL, "
            f"schema_name {t} NOT NULL, "
            f"table_name {t} NOT NULL, "
            f"user_email {t} NOT NULL, "
            f"total_bytes_billed {i} NOT NULL, "
            f"estimated_cost_usd {r} NOT NULL, "
            f"query_count {i} NOT NULL)"
        )

        findings = self._table("findings")
        dbt_findings = self._table("dbt_findings")
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {findings} ("
            f"id {i} NOT NULL, "
            f"created_at {t} NOT NULL, "
            f"connection_name {t} NOT NULL, "
            f"check_type {t} NOT NULL, "
            f"severity {t} NOT NULL, "
            f"schema_name {t} NOT NULL, "
            f"table_name {t} NOT NULL, "
            f"description {t} NOT NULL, "
            f"details {t} NOT NULL)"
        )
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {dbt_findings} ("
            f"id {i} NOT NULL, "
            f"created_at {t} NOT NULL, "
            f"resource_type {t} NOT NULL, "
            f"severity {t} NOT NULL, "
            f"unique_id {t} NOT NULL, "
            f"status {t} NOT NULL, "
            f"execution_time {r} NOT NULL, "
            f"description {t} NOT NULL, "
            f"details {t} NOT NULL)"
        )

        if self._indexes:
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_schema_sid "
                f"ON {schema_snap}(snapshot_id)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_volume_sid "
                f"ON {volume_snap}(snapshot_id)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_cost_run_id "
                f"ON {cost_records}(cost_run_id)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_findings_created "
                f"ON {findings}(created_at)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_findings_conn "
                f"ON {findings}(connection_name)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_dbt_findings_created "
                f"ON {dbt_findings}(created_at)"
            )

        logger.debug("Initialized warehouse state in schema %s", self._schema)

    def _create_cost_run(self, connection_name: str = "") -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._next_id("cost_runs")
        self._exec(
            f"INSERT INTO {self._table('cost_runs')} (id, created_at, connection_name) "
            f"VALUES ({new_id}, '{_escape(now)}', '{_escape(connection_name)}')"
        )
        return new_id

    def close(self) -> None:
        pass  # Does not own the connection

    def clean(self) -> None:
        pass  # Warehouse state is managed externally
