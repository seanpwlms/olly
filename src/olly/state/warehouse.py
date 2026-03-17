"""Warehouse-backed state store implementation."""

from __future__ import annotations

import logging
import time
from typing import Any

from olly.logging import timed_raw_sql
from olly.state.base import BaseStateStore

logger = logging.getLogger(__name__)

# Per-dialect SQL type mappings and quoting
_DIALECTS: dict[str, dict[str, Any]] = {
    "duckdb": {
        "text": "VARCHAR",
        "integer": "BIGINT",
        "real": "DOUBLE",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": True,
        "primary_key": True,
    },
    "postgres": {
        "text": "TEXT",
        "integer": "BIGINT",
        "real": "DOUBLE PRECISION",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": True,
        "primary_key": True,
    },
    "snowflake": {
        "text": "VARCHAR",
        "integer": "BIGINT",
        "real": "DOUBLE",
        "boolean": "BOOLEAN",
        "quote": lambda s: f'"{s}"',
        "indexes": False,
        "primary_key": True,
    },
    "bigquery": {
        "text": "STRING",
        "integer": "INT64",
        "real": "FLOAT64",
        "boolean": "BOOL",
        "quote": lambda s: f"`{s}`",
        "indexes": False,
        "primary_key": False,
    },
}

# Monotonic counter to avoid ID collisions within a single process
_id_counter = 0


def _escape(value: str, *, backslash: bool = False) -> str:
    """Escape a string value for SQL literal inclusion.

    BigQuery does not treat ``''`` as an escaped single quote; it sees
    two adjacent string literals that get implicitly concatenated.  Use
    backslash escaping (``\\'``) for BigQuery, standard doubling for
    other dialects.
    """
    if backslash:
        return value.replace("\\", "\\\\").replace("'", "\\'")
    return value.replace("'", "''")


class WarehouseStateStore(BaseStateStore):
    """State store backed by tables in the connected data warehouse.

    IDs are generated using microsecond timestamps with a monotonic
    in-process counter to avoid collisions within a single process.
    Concurrent processes are unlikely to collide but this is not fully
    ACID-safe across multiple independent ``olly`` invocations.
    """

    _BATCH_SIZE = 500

    def __init__(
        self, conn: Any, schema: str, conn_type: str,
        *, create_tables: bool = False,
    ) -> None:
        self._conn = conn
        self._schema = schema
        self._conn_type = conn_type
        dialect = _DIALECTS.get(conn_type, _DIALECTS["postgres"])
        self._quote = dialect["quote"]
        self._text = dialect["text"]
        self._integer = dialect["integer"]
        self._real = dialect["real"]
        self._boolean = dialect["boolean"]
        self._indexes = dialect["indexes"]
        self._primary_key = dialect["primary_key"]
        if create_tables:
            self._init_tables()

    #: Logical table names created in the state schema.
    TABLE_NAMES: list[str] = [
        "snapshots",
        "schema_snapshot",
        "volume_snapshot",
        "cost_runs",
        "cost_records",
        "findings",
        "dbt_findings",
        "finding_dispositions",
        "dbt_runs",
        "dbt_node_timings",
    ]

    def _table(self, name: str) -> str:
        return f"{self._quote(self._schema)}.{self._quote(name)}"

    def _esc(self, value: str) -> str:
        """Escape a string literal using the correct strategy for this dialect."""
        return _escape(value, backslash=self._conn_type == "bigquery")

    def _exec(self, sql: str) -> Any:
        return timed_raw_sql(self._conn, sql)

    def _fetchall(self, result: Any) -> list[tuple]:
        """Convert a query result to a list of tuples.

        Handles both DBAPI cursors (which have ``fetchall``) and BigQuery's
        ``RowIterator`` (which is iterable but lacks ``fetchall``).
        """
        if hasattr(result, "fetchall"):
            return result.fetchall()
        # BigQuery RowIterator: rows are dict-like objects
        return [tuple(row.values()) for row in result]

    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        resolved = self._resolve_params(sql, params)
        result = self._exec(resolved)
        return self._fetchall(result)

    def _execute(self, sql: str, params: dict[str, Any] | None = None) -> int | None:
        resolved = self._resolve_params(sql, params)
        self._exec(resolved)
        # Warehouse doesn't support lastrowid; use _next_id for snapshots
        return None

    def _format_row(self, row: tuple) -> str:
        """Format a single row tuple as a SQL VALUES literal."""
        parts = []
        for val in row:
            if isinstance(val, str):
                parts.append(f"'{self._esc(val)}'")
            elif isinstance(val, bool):
                parts.append("1" if val else "0")
            elif val is None:
                parts.append("NULL")
            else:
                parts.append(str(val))
        return f"({', '.join(parts)})"

    def _execute_many(
        self, sql: str, column_names: list[str], rows: list[tuple]
    ) -> None:
        if not rows:
            return
        # Extract the table and column part from the SQL template
        # e.g., "INSERT INTO schema.table (col1, col2) VALUES (:col1, :col2)"
        values_idx = sql.upper().index("VALUES")
        prefix = sql[:values_idx]

        for i in range(0, len(rows), self._BATCH_SIZE):
            batch = rows[i : i + self._BATCH_SIZE]
            values = [self._format_row(row) for row in batch]
            self._exec(f"{prefix}VALUES {', '.join(values)}")

    def _resolve_params(self, sql: str, params: dict[str, Any] | None) -> str:
        """Replace :name placeholders with escaped literal values."""
        if params is None:
            return sql
        import re
        def replacer(m: re.Match) -> str:
            name = m.group(1)
            val = params[name]
            if isinstance(val, str):
                return f"'{self._esc(val)}'"
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

    # Override create_snapshot to use _generate_id since warehouse has no AUTOINCREMENT
    def _generate_id(self) -> int:
        """Generate a unique ID using microsecond timestamps.

        Uses ``time.time_ns() // 1000`` (microseconds since epoch) combined
        with a monotonic in-process counter to guarantee uniqueness within a
        single process. Concurrent processes are unlikely to collide given
        microsecond resolution, but this is not fully ACID-safe across
        multiple independent processes.
        """
        global _id_counter  # noqa: PLW0603
        ts = time.time_ns() // 1000
        _id_counter += 1
        return ts + _id_counter

    def create_snapshot(self, connection_name: str = "") -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._generate_id()
        self._exec(
            f"INSERT INTO {self._table('snapshots')} (id, created_at, connection_name) "
            f"VALUES ({new_id}, '{self._esc(now)}', '{self._esc(connection_name)}')"
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
        finding_id = self._generate_id()
        all_values = []
        for f in findings:
            details_json = self._esc(json.dumps(f.details))
            all_values.append(
                f"({finding_id}, '{self._esc(now)}', '{self._esc(f.connection_name)}', "
                f"'{self._esc(f.check_type)}', '{self._esc(f.severity)}', "
                f"'{self._esc(f.schema_name)}', '{self._esc(f.table_name)}', "
                f"'{self._esc(f.description)}', '{details_json}')"
            )
            finding_id += 1
        prefix = (
            f"INSERT INTO {self._table('findings')} "
            f"(id, created_at, connection_name, check_type, severity, schema_name, "
            f"table_name, description, details) "
        )
        for i in range(0, len(all_values), self._BATCH_SIZE):
            batch = all_values[i : i + self._BATCH_SIZE]
            self._exec(f"{prefix}VALUES {', '.join(batch)}")
        logger.debug("Stored %d findings to warehouse", len(findings))

    def store_dbt_findings(
        self, dbt_findings: list, *, dbt_run_id: int | None = None,
    ) -> None:
        """Override to include auto-generated IDs for warehouse."""
        if not dbt_findings:
            return
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        finding_id = self._generate_id()
        run_id_sql = str(dbt_run_id) if dbt_run_id is not None else "NULL"
        all_values = []
        for f in dbt_findings:
            details_json = self._esc(json.dumps(f.details))
            all_values.append(
                f"({finding_id}, '{self._esc(now)}', '{self._esc(f.resource_type)}', "
                f"'{self._esc(f.severity)}', '{self._esc(f.unique_id)}', "
                f"'{self._esc(f.status)}', {f.execution_time}, "
                f"'{self._esc(f.description)}', '{details_json}', {run_id_sql})"
            )
            finding_id += 1
        prefix = (
            f"INSERT INTO {self._table('dbt_findings')} "
            f"(id, created_at, resource_type, severity, unique_id, status, "
            f"execution_time, description, details, dbt_run_id) "
        )
        for i in range(0, len(all_values), self._BATCH_SIZE):
            batch = all_values[i : i + self._BATCH_SIZE]
            self._exec(f"{prefix}VALUES {', '.join(batch)}")
        logger.debug("Stored %d dbt findings to warehouse", len(dbt_findings))

    def _init_tables(self) -> None:
        schema_q = self._quote(self._schema)
        self._exec(f"CREATE SCHEMA IF NOT EXISTS {schema_q}")

        t = self._text
        i = self._integer
        r = self._real
        b = self._boolean
        pk = " PRIMARY KEY" if self._primary_key else ""
        snapshots = self._table("snapshots")
        schema_snap = self._table("schema_snapshot")
        volume_snap = self._table("volume_snapshot")
        cost_runs = self._table("cost_runs")
        cost_records = self._table("cost_records")

        self._exec(
            f"CREATE TABLE IF NOT EXISTS {snapshots} ("
            f"id {i} NOT NULL{pk}, "
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
            f"id {i} NOT NULL{pk}, "
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
            f"id {i} NOT NULL{pk}, "
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
            f"id {i} NOT NULL{pk}, "
            f"created_at {t} NOT NULL, "
            f"resource_type {t} NOT NULL, "
            f"severity {t} NOT NULL, "
            f"unique_id {t} NOT NULL, "
            f"status {t} NOT NULL, "
            f"execution_time {r} NOT NULL, "
            f"description {t} NOT NULL, "
            f"details {t} NOT NULL, "
            f"dbt_run_id {i})"
        )

        dispositions = self._table("finding_dispositions")
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {dispositions} ("
            f"id {i} NOT NULL{pk}, "
            f"finding_id {i} NOT NULL, "
            f"disposition {t} NOT NULL, "
            f"comment {t} NOT NULL, "
            f"created_at {t} NOT NULL, "
            f"created_by {t} NOT NULL)"
        )

        dbt_runs = self._table("dbt_runs")
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {dbt_runs} ("
            f"id {i} NOT NULL{pk}, "
            f"created_at {t} NOT NULL, "
            f"invocation_id {t} NOT NULL, "
            f"elapsed_time {r} NOT NULL, "
            f"total_nodes {i} NOT NULL, "
            f"error_count {i} NOT NULL, "
            f"warning_count {i} NOT NULL, "
            f"pass_count {i} NOT NULL)"
        )

        dbt_node_timings = self._table("dbt_node_timings")
        self._exec(
            f"CREATE TABLE IF NOT EXISTS {dbt_node_timings} ("
            f"id {i} NOT NULL{pk}, "
            f"dbt_run_id {i} NOT NULL, "
            f"unique_id {t} NOT NULL, "
            f"resource_type {t} NOT NULL, "
            f"execution_time {r} NOT NULL, "
            f"status {t} NOT NULL)"
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
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_dispositions_fid "
                f"ON {dispositions}(finding_id)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_dbt_runs_created "
                f"ON {dbt_runs}(created_at)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_dbt_node_timings_run "
                f"ON {dbt_node_timings}(dbt_run_id)"
            )
            self._exec(
                f"CREATE INDEX IF NOT EXISTS idx_wss_dbt_node_timings_uid "
                f"ON {dbt_node_timings}(unique_id)"
            )

        logger.debug("Initialized warehouse state in schema %s", self._schema)

    def _create_cost_run(self, connection_name: str = "") -> int:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._generate_id()
        self._exec(
            f"INSERT INTO {self._table('cost_runs')} (id, created_at, connection_name) "
            f"VALUES ({new_id}, '{self._esc(now)}', '{self._esc(connection_name)}')"
        )
        return new_id

    def set_disposition(
        self, finding_id: int, disposition: str,
        comment: str = "", created_by: str = "",
    ) -> int:
        """Override to use generated IDs for warehouse backends."""
        from datetime import datetime, timezone

        from olly.models import Disposition

        valid = {d.value for d in Disposition}
        if disposition not in valid:
            msg = f"Invalid disposition {disposition!r}, must be one of {valid}"
            raise ValueError(msg)
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._generate_id()
        self._exec(
            f"INSERT INTO {self._table('finding_dispositions')} "
            f"(id, finding_id, disposition, comment, created_at, created_by) "
            f"VALUES ({new_id}, {finding_id}, '{self._esc(disposition)}', "
            f"'{self._esc(comment)}', '{self._esc(now)}', '{self._esc(created_by)}')"
        )
        return new_id

    def store_dbt_run(self, run_record) -> int:
        """Override to use generated IDs for warehouse backends."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._generate_id()
        self._exec(
            f"INSERT INTO {self._table('dbt_runs')} "
            f"(id, created_at, invocation_id, elapsed_time, total_nodes, "
            f"error_count, warning_count, pass_count) "
            f"VALUES ({new_id}, '{self._esc(now)}', '{self._esc(run_record.invocation_id)}', "
            f"{run_record.elapsed_time}, {run_record.total_nodes}, "
            f"{run_record.error_count}, {run_record.warning_count}, {run_record.pass_count})"
        )
        return new_id

    def close(self) -> None:
        pass  # Does not own the connection

    def clean(self) -> None:
        pass  # Warehouse state is managed externally
