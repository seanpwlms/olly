"""Base state store with shared business logic for all backends."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Self

from olly.models import ColumnInfo, CostRecord, DbtFinding, Finding, TableInfo, VolumeRecord

if TYPE_CHECKING:
    from olly.config import OllyConfig

logger = logging.getLogger(__name__)

_SNAPSHOT_TABLES = ("schema_snapshot", "volume_snapshot", "cost_snapshot")


class BaseStateStore(ABC):
    """Abstract base with all shared business logic.

    Subclasses provide SQL execution primitives and table name resolution.
    """

    @abstractmethod
    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        """Execute a SELECT and return all rows."""

    def _query_one(self, sql: str, params: dict[str, Any] | None = None) -> tuple | None:
        """Execute a SELECT and return one row or None."""
        rows = self._query(sql, params)
        return rows[0] if rows else None

    @abstractmethod
    def _execute(self, sql: str, params: dict[str, Any] | None = None) -> int | None:
        """Execute an INSERT/DELETE and return lastrowid (or None)."""

    @abstractmethod
    def _execute_many(
        self, sql: str, column_names: list[str], rows: list[tuple]
    ) -> None:
        """Batch INSERT rows."""

    @abstractmethod
    def _table(self, name: str) -> str:
        """Return the qualified table name for the given logical name."""

    @abstractmethod
    def _init_tables(self) -> None:
        """Create tables/indexes (dialect-specific DDL)."""

    @abstractmethod
    def close(self) -> None:
        """Close underlying resources."""

    # --- Context manager ---

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        self.close()

    # --- Snapshot management ---

    def create_snapshot(self, connection_name: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        lastrowid = self._execute(
            f"INSERT INTO {self._table('snapshots')} (created_at, connection_name) "  # noqa: S608
            "VALUES (:created_at, :connection_name)",
            {"created_at": now, "connection_name": connection_name},
        )
        assert lastrowid is not None
        logger.debug("Created snapshot #%d", lastrowid)
        return lastrowid

    # --- Store data ---

    def store_schema_data(self, snapshot_id: int, tables: list[TableInfo]) -> None:
        if not tables:
            return
        rows = []
        for t in tables:
            for c in t.columns:
                rows.append((
                    snapshot_id,
                    t.schema_name,
                    t.table_name,
                    t.table_type,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                ))
        self._execute_many(
            f"INSERT INTO {self._table('schema_snapshot')} "  # noqa: S608
            "(snapshot_id, schema_name, table_name, table_type, column_name, data_type, is_nullable) "
            "VALUES (:snapshot_id, :schema_name, :table_name, :table_type, :column_name, :data_type, :is_nullable)",
            ["snapshot_id", "schema_name", "table_name", "table_type", "column_name", "data_type", "is_nullable"],
            rows,
        )

    def store_volume_data(self, snapshot_id: int, volumes: list[VolumeRecord]) -> None:
        if not volumes:
            return
        rows = [
            (snapshot_id, v.schema_name, v.table_name, v.row_count) for v in volumes
        ]
        self._execute_many(
            f"INSERT INTO {self._table('volume_snapshot')} "  # noqa: S608
            "(snapshot_id, schema_name, table_name, row_count) "
            "VALUES (:snapshot_id, :schema_name, :table_name, :row_count)",
            ["snapshot_id", "schema_name", "table_name", "row_count"],
            rows,
        )

    def store_cost_data(self, snapshot_id: int, records: list[CostRecord]) -> None:
        if not records:
            return
        rows = [
            (
                snapshot_id,
                r.schema_name,
                r.table_name,
                r.user_email,
                r.total_bytes_billed,
                r.estimated_cost_usd,
                r.query_count,
            )
            for r in records
        ]
        self._execute_many(
            f"INSERT INTO {self._table('cost_snapshot')} "  # noqa: S608
            "(snapshot_id, schema_name, table_name, user_email, "
            "total_bytes_billed, estimated_cost_usd, query_count) "
            "VALUES (:snapshot_id, :schema_name, :table_name, :user_email, "
            ":total_bytes_billed, :estimated_cost_usd, :query_count)",
            ["snapshot_id", "schema_name", "table_name", "user_email",
             "total_bytes_billed", "estimated_cost_usd", "query_count"],
            rows,
        )

    # --- Latest snapshot helpers ---

    def _get_latest_snapshot_id(self, connection_name: str = "") -> int | None:
        row = self._query_one(
            f"SELECT id FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name "
            "ORDER BY id DESC LIMIT 1",
            {"connection_name": connection_name},
        )
        return row[0] if row is not None else None

    def _get_recent_snapshot_ids(
        self, limit: int, connection_name: str = ""
    ) -> list[int]:
        rows = self._query(
            f"SELECT id FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name "
            "ORDER BY id DESC LIMIT :limit",
            {"connection_name": connection_name, "limit": limit},
        )
        return [r[0] for r in rows]

    def get_latest_schema(self, connection_name: str = "") -> list[TableInfo]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_schema_for_snapshot(snapshot_id)

    def get_second_latest_schema(self, connection_name: str = "") -> list[TableInfo]:
        snapshot_ids = self._get_recent_snapshot_ids(2, connection_name)
        if len(snapshot_ids) < 2:
            return []
        return self._load_schema_for_snapshot(snapshot_ids[1])

    def get_latest_volume(self, connection_name: str = "") -> list[VolumeRecord]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_volume_for_snapshot(snapshot_id)

    def get_second_latest_volume(
        self, connection_name: str = ""
    ) -> list[VolumeRecord]:
        snapshot_ids = self._get_recent_snapshot_ids(2, connection_name)
        if len(snapshot_ids) < 2:
            return []
        return self._load_volume_for_snapshot(snapshot_ids[1])

    def get_latest_cost(self, connection_name: str = "") -> list[CostRecord]:
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self.get_cost_records_for_snapshot(snapshot_id)

    # --- Schema loading ---

    def _load_schema_for_snapshot(self, snapshot_id: int) -> list[TableInfo]:
        rows = self._query(
            f"SELECT schema_name, table_name, table_type, column_name, data_type, is_nullable "  # noqa: S608
            f"FROM {self._table('schema_snapshot')} WHERE snapshot_id = :snapshot_id "
            "ORDER BY schema_name, table_name, column_name",
            {"snapshot_id": snapshot_id},
        )
        tables: dict[tuple[str, str], TableInfo] = {}
        for schema_name, table_name, table_type, col_name, data_type, is_nullable in rows:
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
        rows = self._query(
            f"SELECT schema_name, table_name, row_count "  # noqa: S608
            f"FROM {self._table('volume_snapshot')} WHERE snapshot_id = :snapshot_id",
            {"snapshot_id": snapshot_id},
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
        rows = self._query(
            f"SELECT v.row_count FROM {self._table('volume_snapshot')} v "  # noqa: S608
            f"JOIN {self._table('snapshots')} s ON v.snapshot_id = s.id "
            "WHERE v.schema_name = :schema_name AND v.table_name = :table_name "
            "AND s.connection_name = :connection_name "
            "ORDER BY s.id DESC LIMIT :depth",
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "connection_name": connection_name,
                "depth": depth,
            },
        )
        return [r[0] for r in rows]

    def get_recent_volume_unchanged_count(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> int:
        history = self.get_volume_history(
            schema_name, table_name, depth, connection_name
        )
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
        row = self._query_one(
            f"SELECT COUNT(*) FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name",
            {"connection_name": connection_name},
        )
        total = row[0] if row else 0
        if total <= keep:
            return
        logger.debug("Pruning snapshots older than depth %d", keep)
        rows = self._query(
            f"SELECT id FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name "
            "ORDER BY id ASC LIMIT :limit",
            {"connection_name": connection_name, "limit": total - keep},
        )
        ids = [r[0] for r in rows]
        self._delete_by_ids("schema_snapshot", "snapshot_id", ids)
        self._delete_by_ids("volume_snapshot", "snapshot_id", ids)
        self._delete_by_ids("cost_snapshot", "snapshot_id", ids)
        self._delete_by_ids("snapshots", "id", ids)

    @abstractmethod
    def _delete_by_ids(self, table: str, column: str, ids: list[int]) -> None:
        """Delete rows where column IN (ids). Dialect-specific."""

    # --- Cost history ---

    def get_cost_history(
        self, depth: int, connection_name: str = ""
    ) -> list[tuple[int, float]]:
        rows = self._query(
            f"SELECT c.snapshot_id, SUM(c.estimated_cost_usd) AS total_cost "  # noqa: S608
            f"FROM {self._table('cost_snapshot')} c "
            f"JOIN {self._table('snapshots')} s ON c.snapshot_id = s.id "
            "WHERE s.connection_name = :connection_name "
            "GROUP BY c.snapshot_id "
            "ORDER BY c.snapshot_id DESC LIMIT :depth",
            {"connection_name": connection_name, "depth": depth},
        )
        return [(r[0], r[1]) for r in rows]

    def get_cost_records_for_snapshot(self, snapshot_id: int) -> list[CostRecord]:
        rows = self._query(
            f"SELECT schema_name, table_name, user_email, "  # noqa: S608
            "total_bytes_billed, estimated_cost_usd, query_count "
            f"FROM {self._table('cost_snapshot')} WHERE snapshot_id = :snapshot_id",
            {"snapshot_id": snapshot_id},
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
        rows = self._query(
            f"SELECT s.created_at, v.row_count FROM {self._table('volume_snapshot')} v "  # noqa: S608
            f"JOIN {self._table('snapshots')} s ON v.snapshot_id = s.id "
            "WHERE v.schema_name = :schema_name AND v.table_name = :table_name "
            "AND s.connection_name = :connection_name "
            "ORDER BY s.id ASC LIMIT :depth",
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "connection_name": connection_name,
                "depth": depth,
            },
        )
        return [(row[0], row[1]) for row in rows]

    def get_table_first_seen(
        self, schema_name: str, table_name: str,
        connection_name: str = "",
    ) -> tuple[str | None, int]:
        row = self._query_one(
            f"SELECT MIN(s.created_at), COUNT(DISTINCT s.id) "  # noqa: S608
            f"FROM {self._table('schema_snapshot')} ss "
            f"JOIN {self._table('snapshots')} s ON ss.snapshot_id = s.id "
            "WHERE ss.schema_name = :schema_name AND ss.table_name = :table_name "
            "AND s.connection_name = :connection_name",
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "connection_name": connection_name,
            },
        )
        if not row or row[0] is None:
            return None, 0
        return row[0], row[1]

    def get_recent_snapshot_ids_for_table(
        self, schema_name: str, table_name: str, limit: int = 2,
        connection_name: str = "",
    ) -> list[int]:
        rows = self._query(
            f"SELECT DISTINCT s.id FROM {self._table('schema_snapshot')} ss "  # noqa: S608
            f"JOIN {self._table('snapshots')} s ON ss.snapshot_id = s.id "
            "WHERE ss.schema_name = :schema_name AND ss.table_name = :table_name "
            "AND s.connection_name = :connection_name "
            "ORDER BY s.id DESC LIMIT :limit",
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "connection_name": connection_name,
                "limit": limit,
            },
        )
        return [r[0] for r in rows]

    def get_columns_for_snapshot(
        self, snapshot_id: int, schema_name: str, table_name: str
    ) -> dict[str, tuple[str, bool]]:
        rows = self._query(
            "SELECT column_name, data_type, is_nullable "
            f"FROM {self._table('schema_snapshot')} "  # noqa: S608
            "WHERE snapshot_id = :snapshot_id AND schema_name = :schema_name "
            "AND table_name = :table_name",
            {
                "snapshot_id": snapshot_id,
                "schema_name": schema_name,
                "table_name": table_name,
            },
        )
        return {r[0]: (r[1], bool(r[2])) for r in rows}

    def has_snapshots(self, connection_name: str = "") -> bool:
        row = self._query_one(
            f"SELECT COUNT(*) FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name",
            {"connection_name": connection_name},
        )
        return bool(row and row[0] > 0)

    def has_multiple_snapshots(self, connection_name: str = "") -> bool:
        row = self._query_one(
            f"SELECT COUNT(*) FROM {self._table('snapshots')} "  # noqa: S608
            "WHERE connection_name = :connection_name",
            {"connection_name": connection_name},
        )
        return bool(row and row[0] >= 2)

    # --- Findings ---

    def store_findings(self, findings: list[Finding]) -> None:
        if not findings:
            return
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                now,
                f.connection_name,
                f.check_type,
                f.severity,
                f.schema_name,
                f.table_name,
                f.description,
                json.dumps(f.details),
            )
            for f in findings
        ]
        self._execute_many(
            f"INSERT INTO {self._table('findings')} "  # noqa: S608
            "(created_at, connection_name, check_type, severity, schema_name, "
            "table_name, description, details) "
            "VALUES (:created_at, :connection_name, :check_type, :severity, "
            ":schema_name, :table_name, :description, :details)",
            ["created_at", "connection_name", "check_type", "severity",
             "schema_name", "table_name", "description", "details"],
            rows,
        )
        logger.debug("Stored %d findings", len(findings))

    def store_dbt_findings(self, dbt_findings: list[DbtFinding]) -> None:
        if not dbt_findings:
            return
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                now,
                f.resource_type,
                f.severity,
                f.unique_id,
                f.status,
                f.execution_time,
                f.description,
                json.dumps(f.details),
            )
            for f in dbt_findings
        ]
        self._execute_many(
            f"INSERT INTO {self._table('dbt_findings')} "  # noqa: S608
            "(created_at, resource_type, severity, unique_id, status, "
            "execution_time, description, details) "
            "VALUES (:created_at, :resource_type, :severity, :unique_id, "
            ":status, :execution_time, :description, :details)",
            ["created_at", "resource_type", "severity", "unique_id",
             "status", "execution_time", "description", "details"],
            rows,
        )
        logger.debug("Stored %d dbt findings", len(dbt_findings))

    def get_findings_history(
        self, limit: int = 100, connection_name: str | None = None
    ) -> list[Finding]:
        if connection_name is not None:
            rows = self._query(
                "SELECT connection_name, check_type, severity, schema_name, "
                f"table_name, description, details "  # noqa: S608
                f"FROM {self._table('findings')} WHERE connection_name = :connection_name "
                "ORDER BY created_at DESC LIMIT :limit",
                {"connection_name": connection_name, "limit": limit},
            )
        else:
            rows = self._query(
                "SELECT connection_name, check_type, severity, schema_name, "
                f"table_name, description, details "  # noqa: S608
                f"FROM {self._table('findings')} ORDER BY created_at DESC LIMIT :limit",
                {"limit": limit},
            )
        return [
            Finding(
                connection_name=r[0],
                check_type=r[1],
                severity=r[2],
                schema_name=r[3],
                table_name=r[4],
                description=r[5],
                details=json.loads(r[6]) if r[6] else {},
            )
            for r in rows
        ]

    def get_dbt_findings_history(self, limit: int = 100) -> list[DbtFinding]:
        rows = self._query(
            "SELECT resource_type, severity, unique_id, status, "
            f"execution_time, description, details "  # noqa: S608
            f"FROM {self._table('dbt_findings')} ORDER BY created_at DESC LIMIT :limit",
            {"limit": limit},
        )
        return [
            DbtFinding(
                resource_type=r[0],
                severity=r[1],
                unique_id=r[2],
                status=r[3],
                execution_time=r[4],
                description=r[5],
                details=json.loads(r[6]) if r[6] else {},
            )
            for r in rows
        ]


def open_state(
    config: OllyConfig, adapter: Any = None
) -> BaseStateStore:
    """Create a state store based on configuration.

    When ``state_schema`` is set and an adapter is provided, state is stored
    in the warehouse. Otherwise falls back to local SQLite.
    """
    if config.settings.state_schema and adapter is not None:
        from olly.state.warehouse import WarehouseStateStore

        conn_type = ""
        # Derive conn_type from adapter or config
        for nc in config.connections.values():
            if nc.connection.type:
                conn_type = nc.connection.type
                break

        return WarehouseStateStore(
            adapter.backend, config.settings.state_schema, conn_type
        )
    from olly.state.sqlite import StateDB

    return StateDB()
