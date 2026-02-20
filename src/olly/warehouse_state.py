from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from olly.models import ColumnInfo, CostRecord, TableInfo, VolumeRecord

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


class WarehouseStateStore:
    """State store backed by tables in the connected data warehouse."""

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
        self._init_schema()

    def _qualified(self, table: str) -> str:
        return f"{self._quote(self._schema)}.{self._quote(table)}"

    def _exec(self, sql: str) -> Any:
        return self._conn.raw_sql(sql)

    def _fetchone(self, sql: str) -> tuple | None:
        result = self._exec(sql)
        return result.fetchone()

    def _fetchall(self, sql: str) -> list[tuple]:
        result = self._exec(sql)
        return result.fetchall()

    def _init_schema(self) -> None:
        schema_q = self._quote(self._schema)
        self._exec(f"CREATE SCHEMA IF NOT EXISTS {schema_q}")

        t = self._text
        i = self._integer
        r = self._real
        b = self._boolean
        snapshots = self._qualified("snapshots")
        schema_snap = self._qualified("schema_snapshot")
        volume_snap = self._qualified("volume_snapshot")
        cost_snap = self._qualified("cost_snapshot")

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
            f"CREATE TABLE IF NOT EXISTS {cost_snap} ("
            f"snapshot_id {i} NOT NULL, "
            f"schema_name {t} NOT NULL, "
            f"table_name {t} NOT NULL, "
            f"user_email {t} NOT NULL, "
            f"total_bytes_billed {i} NOT NULL, "
            f"estimated_cost_usd {r} NOT NULL, "
            f"query_count {i} NOT NULL)"
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
                f"CREATE INDEX IF NOT EXISTS idx_wss_cost_sid "
                f"ON {cost_snap}(snapshot_id)"
            )

        logger.debug("Initialized warehouse state in schema %s", self._schema)

    # --- Snapshot management ---

    def _next_id(self) -> int:
        row = self._fetchone(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {self._qualified('snapshots')}"
        )
        return row[0] if row else 1

    def create_snapshot(self, connection_name: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._next_id()
        self._exec(
            f"INSERT INTO {self._qualified('snapshots')} (id, created_at, connection_name) "
            f"VALUES ({new_id}, '{_escape(now)}', '{_escape(connection_name)}')"
        )
        logger.debug("Created warehouse snapshot #%d", new_id)
        return new_id

    # --- Schema data ---

    def store_schema_data(self, snapshot_id: int, tables: list[TableInfo]) -> None:
        if not tables:
            return
        values = []
        for t in tables:
            for c in t.columns:
                nullable_int = 1 if c.is_nullable else 0
                values.append(
                    f"({snapshot_id}, '{_escape(t.schema_name)}', '{_escape(t.table_name)}', "
                    f"'{_escape(t.table_type)}', '{_escape(c.column_name)}', "
                    f"'{_escape(c.data_type)}', {nullable_int})"
                )
        self._exec(
            f"INSERT INTO {self._qualified('schema_snapshot')} "
            f"(snapshot_id, schema_name, table_name, table_type, column_name, data_type, is_nullable) "
            f"VALUES {', '.join(values)}"
        )

    # --- Volume data ---

    def store_volume_data(self, snapshot_id: int, volumes: list[VolumeRecord]) -> None:
        if not volumes:
            return
        values = [
            f"({snapshot_id}, '{_escape(v.schema_name)}', '{_escape(v.table_name)}', {v.row_count})"
            for v in volumes
        ]
        self._exec(
            f"INSERT INTO {self._qualified('volume_snapshot')} "
            f"(snapshot_id, schema_name, table_name, row_count) "
            f"VALUES {', '.join(values)}"
        )

    # --- Cost data ---

    def store_cost_data(self, snapshot_id: int, records: list[CostRecord]) -> None:
        if not records:
            return
        values = [
            f"({snapshot_id}, '{_escape(r.schema_name)}', '{_escape(r.table_name)}', "
            f"'{_escape(r.user_email)}', {r.total_bytes_billed}, {r.estimated_cost_usd}, "
            f"{r.query_count})"
            for r in records
        ]
        self._exec(
            f"INSERT INTO {self._qualified('cost_snapshot')} "
            f"(snapshot_id, schema_name, table_name, user_email, "
            f"total_bytes_billed, estimated_cost_usd, query_count) "
            f"VALUES {', '.join(values)}"
        )

    # --- Latest snapshot helpers ---

    def _get_latest_snapshot_id(self, connection_name: str = "") -> int | None:
        row = self._fetchone(
            f"SELECT id FROM {self._qualified('snapshots')} "
            f"WHERE connection_name = '{_escape(connection_name)}' "
            f"ORDER BY id DESC LIMIT 1"
        )
        return row[0] if row else None

    def get_latest_schema(self, connection_name: str = "") -> list[TableInfo]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_schema_for_snapshot(snapshot_id)

    def get_latest_volume(self, connection_name: str = "") -> list[VolumeRecord]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_volume_for_snapshot(snapshot_id)

    def get_latest_cost(self, connection_name: str = "") -> list[CostRecord]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self.get_cost_records_for_snapshot(snapshot_id)

    # --- Schema loading ---

    def _load_schema_for_snapshot(self, snapshot_id: int) -> list[TableInfo]:
        rows = self._fetchall(
            f"SELECT schema_name, table_name, table_type, column_name, data_type, is_nullable "
            f"FROM {self._qualified('schema_snapshot')} WHERE snapshot_id = {snapshot_id} "
            f"ORDER BY schema_name, table_name, column_name"
        )
        tables: dict[tuple[str, str], TableInfo] = {}
        for (
            schema_name,
            table_name,
            table_type,
            col_name,
            data_type,
            is_nullable,
        ) in rows:
            key = (schema_name, table_name)
            if key not in tables:
                tables[key] = TableInfo(
                    schema_name=schema_name,
                    table_name=table_name,
                    table_type=table_type,
                    columns=[],
                )
            tables[key].columns.append(
                ColumnInfo(
                    column_name=col_name,
                    data_type=data_type,
                    is_nullable=bool(is_nullable),
                )
            )
        return list(tables.values())

    # --- Volume loading ---

    def _load_volume_for_snapshot(self, snapshot_id: int) -> list[VolumeRecord]:
        rows = self._fetchall(
            f"SELECT schema_name, table_name, row_count "
            f"FROM {self._qualified('volume_snapshot')} WHERE snapshot_id = {snapshot_id}"
        )
        return [
            VolumeRecord(schema_name=r[0], table_name=r[1], row_count=r[2])
            for r in rows
        ]

    # --- Volume history ---

    def get_volume_history(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> list[int]:
        rows = self._fetchall(
            f"SELECT v.row_count FROM {self._qualified('volume_snapshot')} v "
            f"JOIN {self._qualified('snapshots')} s ON v.snapshot_id = s.id "
            f"WHERE v.schema_name = '{_escape(schema_name)}' "
            f"AND v.table_name = '{_escape(table_name)}' "
            f"AND s.connection_name = '{_escape(connection_name)}' "
            f"ORDER BY s.id DESC LIMIT {depth}"
        )
        return [r[0] for r in rows]

    def get_recent_volume_unchanged_count(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> int:
        history = self.get_volume_history(schema_name, table_name, depth, connection_name)
        if len(history) < 2:
            return 0
        count = 1
        for i in range(1, len(history)):
            if history[i] == history[0]:
                count += 1
            else:
                break
        return count

    # --- Pruning ---

    def prune_old_snapshots(self, keep: int, connection_name: str = "") -> None:
        row = self._fetchone(
            f"SELECT COUNT(*) FROM {self._qualified('snapshots')} "
            f"WHERE connection_name = '{_escape(connection_name)}'"
        )
        total = row[0] if row else 0
        if total <= keep:
            return
        logger.debug("Pruning warehouse snapshots older than depth %d", keep)
        rows = self._fetchall(
            f"SELECT id FROM {self._qualified('snapshots')} "
            f"WHERE connection_name = '{_escape(connection_name)}' "
            f"ORDER BY id ASC LIMIT {total - keep}"
        )
        ids = [r[0] for r in rows]
        id_list = ", ".join(str(i) for i in ids)
        for table in ("schema_snapshot", "volume_snapshot", "cost_snapshot"):
            self._exec(
                f"DELETE FROM {self._qualified(table)} WHERE snapshot_id IN ({id_list})"
            )
        self._exec(
            f"DELETE FROM {self._qualified('snapshots')} WHERE id IN ({id_list})"
        )

    # --- Cost history ---

    def get_cost_history(
        self, depth: int, connection_name: str = ""
    ) -> list[tuple[int, float]]:
        rows = self._fetchall(
            f"SELECT c.snapshot_id, SUM(c.estimated_cost_usd) AS total_cost "
            f"FROM {self._qualified('cost_snapshot')} c "
            f"JOIN {self._qualified('snapshots')} s ON c.snapshot_id = s.id "
            f"WHERE s.connection_name = '{_escape(connection_name)}' "
            f"GROUP BY c.snapshot_id "
            f"ORDER BY c.snapshot_id DESC LIMIT {depth}"
        )
        return [(r[0], r[1]) for r in rows]

    def get_cost_records_for_snapshot(self, snapshot_id: int) -> list[CostRecord]:
        rows = self._fetchall(
            f"SELECT schema_name, table_name, user_email, "
            f"total_bytes_billed, estimated_cost_usd, query_count "
            f"FROM {self._qualified('cost_snapshot')} WHERE snapshot_id = {snapshot_id}"
        )
        return [
            CostRecord(
                schema_name=r[0],
                table_name=r[1],
                user_email=r[2],
                total_bytes_billed=r[3],
                estimated_cost_usd=r[4],
                query_count=r[5],
            )
            for r in rows
        ]

    # --- Timeseries and history ---

    def get_volume_timeseries(
        self, schema_name: str, table_name: str, depth: int = 30,
        connection_name: str = "",
    ) -> list[tuple[str, int]]:
        rows = self._fetchall(
            f"SELECT s.created_at, v.row_count FROM {self._qualified('volume_snapshot')} v "
            f"JOIN {self._qualified('snapshots')} s ON v.snapshot_id = s.id "
            f"WHERE v.schema_name = '{_escape(schema_name)}' "
            f"AND v.table_name = '{_escape(table_name)}' "
            f"AND s.connection_name = '{_escape(connection_name)}' "
            f"ORDER BY s.id ASC LIMIT {depth}"
        )
        return [(row[0], row[1]) for row in rows]

    def get_table_first_seen(
        self, schema_name: str, table_name: str,
        connection_name: str = "",
    ) -> tuple[str | None, int]:
        row = self._fetchone(
            f"SELECT MIN(s.created_at), COUNT(DISTINCT s.id) "
            f"FROM {self._qualified('schema_snapshot')} ss "
            f"JOIN {self._qualified('snapshots')} s ON ss.snapshot_id = s.id "
            f"WHERE ss.schema_name = '{_escape(schema_name)}' "
            f"AND ss.table_name = '{_escape(table_name)}' "
            f"AND s.connection_name = '{_escape(connection_name)}'"
        )
        if not row or row[0] is None:
            return None, 0
        return row[0], row[1]

    def get_recent_snapshot_ids_for_table(
        self, schema_name: str, table_name: str, limit: int = 2,
        connection_name: str = "",
    ) -> list[int]:
        rows = self._fetchall(
            f"SELECT DISTINCT s.id FROM {self._qualified('schema_snapshot')} ss "
            f"JOIN {self._qualified('snapshots')} s ON ss.snapshot_id = s.id "
            f"WHERE ss.schema_name = '{_escape(schema_name)}' "
            f"AND ss.table_name = '{_escape(table_name)}' "
            f"AND s.connection_name = '{_escape(connection_name)}' "
            f"ORDER BY s.id DESC LIMIT {limit}"
        )
        return [r[0] for r in rows]

    def get_columns_for_snapshot(
        self, snapshot_id: int, schema_name: str, table_name: str
    ) -> dict[str, tuple[str, bool]]:
        rows = self._fetchall(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM {self._qualified('schema_snapshot')} "
            f"WHERE snapshot_id = {snapshot_id} "
            f"AND schema_name = '{_escape(schema_name)}' "
            f"AND table_name = '{_escape(table_name)}'"
        )
        return {r[0]: (r[1], bool(r[2])) for r in rows}

    def has_snapshots(self, connection_name: str = "") -> bool:
        row = self._fetchone(
            f"SELECT COUNT(*) FROM {self._qualified('snapshots')} "
            f"WHERE connection_name = '{_escape(connection_name)}'"
        )
        return bool(row and row[0] > 0)

    def close(self) -> None:
        pass  # Does not own the connection

    def __enter__(self) -> WarehouseStateStore:
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        self.close()
