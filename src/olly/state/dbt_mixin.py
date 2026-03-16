"""dbt findings and run history state mixin."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from olly.models import DbtFinding, DbtRunRecord

logger = logging.getLogger(__name__)


class DbtStateMixin:
    """Methods for storing and querying dbt findings, runs, and node timings.

    Mixed into BaseStateStore — relies on _query, _query_one, _execute,
    _execute_many, and _table being available via MRO.
    """

    # Stubs so ty knows about inherited methods from BaseStateStore.
    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        raise NotImplementedError
    def _query_one(self, sql: str, params: dict[str, Any] | None = None) -> tuple | None:
        raise NotImplementedError
    def _execute(self, sql: str, params: dict[str, Any] | None = None) -> int | None:
        raise NotImplementedError
    def _execute_many(self, sql: str, column_names: list[str], rows: list[tuple]) -> None:
        raise NotImplementedError
    def _table(self, name: str) -> str:
        raise NotImplementedError

    def store_dbt_findings(
        self, dbt_findings: list[DbtFinding], *, dbt_run_id: int | None = None,
    ) -> None:
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
                dbt_run_id,
            )
            for f in dbt_findings
        ]
        self._execute_many(
            f"INSERT INTO {self._table('dbt_findings')} "  # noqa: S608
            "(created_at, resource_type, severity, unique_id, status, "
            "execution_time, description, details, dbt_run_id) "
            "VALUES (:created_at, :resource_type, :severity, :unique_id, "
            ":status, :execution_time, :description, :details, :dbt_run_id)",
            ["created_at", "resource_type", "severity", "unique_id",
             "status", "execution_time", "description", "details", "dbt_run_id"],
            rows,
        )
        logger.debug("Stored %d dbt findings", len(dbt_findings))

    def get_latest_dbt_findings(self) -> list[DbtFinding]:
        """Return dbt findings from the most recent check run only."""
        row = self._query_one(
            f"SELECT MAX(created_at) FROM {self._table('dbt_findings')}"
        )
        last_check = row[0] if row and row[0] else None
        if not last_check:
            return []
        rows = self._query(
            "SELECT resource_type, severity, unique_id, status, "
            f"execution_time, description, details, dbt_run_id "  # noqa: S608
            f"FROM {self._table('dbt_findings')} WHERE created_at = :created_at",
            {"created_at": last_check},
        )
        return self._rows_to_dbt_findings(rows)

    def get_dbt_findings_history(self, limit: int = 100) -> list[DbtFinding]:
        rows = self._query(
            "SELECT resource_type, severity, unique_id, status, "
            f"execution_time, description, details, dbt_run_id "  # noqa: S608
            f"FROM {self._table('dbt_findings')} ORDER BY created_at DESC LIMIT :limit",
            {"limit": limit},
        )
        return self._rows_to_dbt_findings(rows)

    def _rows_to_dbt_findings(self, rows: list[tuple]) -> list[DbtFinding]:
        return [
            DbtFinding(
                resource_type=r[0],
                severity=r[1],
                unique_id=r[2],
                status=r[3],
                execution_time=r[4],
                description=r[5],
                details=json.loads(r[6]) if r[6] else {},
                dbt_run_id=r[7] if len(r) > 7 else None,
            )
            for r in rows
        ]

    def get_previous_compiled_code(
        self, unique_id: str, current_run_id: int | None = None,
    ) -> str | None:
        """Return compiled_code from the previous dbt run for a node."""
        if current_run_id is not None:
            row = self._query_one(
                f"SELECT details FROM {self._table('dbt_findings')} "  # noqa: S608
                "WHERE unique_id = :unique_id AND dbt_run_id < :run_id "
                "ORDER BY dbt_run_id DESC LIMIT 1",
                {"unique_id": unique_id, "run_id": current_run_id},
            )
        else:
            rows = self._query(
                f"SELECT details FROM {self._table('dbt_findings')} "  # noqa: S608
                "WHERE unique_id = :unique_id "
                "ORDER BY created_at DESC LIMIT 2",
                {"unique_id": unique_id},
            )
            row = rows[1] if len(rows) >= 2 else None
        if row is None:
            return None
        details = json.loads(row[0]) if row[0] else {}
        return details.get("compiled_code")

    # --- dbt run history ---

    def store_dbt_run(self, run_record: DbtRunRecord) -> int:
        """Store a dbt run summary. Returns the run ID."""
        now = datetime.now(timezone.utc).isoformat()
        lastrowid = self._execute(
            f"INSERT INTO {self._table('dbt_runs')} "  # noqa: S608
            "(created_at, invocation_id, elapsed_time, total_nodes, "
            "error_count, warning_count, pass_count) "
            "VALUES (:created_at, :invocation_id, :elapsed_time, :total_nodes, "
            ":error_count, :warning_count, :pass_count)",
            {
                "created_at": now,
                "invocation_id": run_record.invocation_id,
                "elapsed_time": run_record.elapsed_time,
                "total_nodes": run_record.total_nodes,
                "error_count": run_record.error_count,
                "warning_count": run_record.warning_count,
                "pass_count": run_record.pass_count,
            },
        )
        assert lastrowid is not None
        logger.debug("Stored dbt run #%d", lastrowid)
        return lastrowid

    def store_dbt_node_timings(
        self, dbt_run_id: int, findings: list[DbtFinding],
    ) -> None:
        """Store per-node execution timings for a dbt run."""
        if not findings:
            return
        rows = [
            (dbt_run_id, f.unique_id, f.resource_type, f.execution_time, f.status)
            for f in findings
        ]
        self._execute_many(
            f"INSERT INTO {self._table('dbt_node_timings')} "  # noqa: S608
            "(dbt_run_id, unique_id, resource_type, execution_time, status) "
            "VALUES (:dbt_run_id, :unique_id, :resource_type, :execution_time, :status)",
            ["dbt_run_id", "unique_id", "resource_type", "execution_time", "status"],
            rows,
        )

    def get_dbt_run_history(self, limit: int = 30) -> list[DbtRunRecord]:
        """Return dbt run records, newest first."""
        rows = self._query(
            "SELECT invocation_id, elapsed_time, total_nodes, "  # noqa: S608
            f"error_count, warning_count, pass_count FROM {self._table('dbt_runs')} "
            "ORDER BY id DESC LIMIT :limit",
            {"limit": limit},
        )
        return [
            DbtRunRecord(
                invocation_id=r[0],
                elapsed_time=r[1],
                total_nodes=r[2],
                error_count=r[3],
                warning_count=r[4],
                pass_count=r[5],
            )
            for r in rows
        ]

    def get_dbt_run_history_with_timestamps(self, limit: int = 30) -> list[tuple[str, DbtRunRecord]]:
        """Return (created_at, DbtRunRecord) tuples, newest first."""
        rows = self._query(
            "SELECT created_at, invocation_id, elapsed_time, total_nodes, "  # noqa: S608
            f"error_count, warning_count, pass_count FROM {self._table('dbt_runs')} "
            "ORDER BY id DESC LIMIT :limit",
            {"limit": limit},
        )
        return [
            (
                r[0],
                DbtRunRecord(
                    invocation_id=r[1],
                    elapsed_time=r[2],
                    total_nodes=r[3],
                    error_count=r[4],
                    warning_count=r[5],
                    pass_count=r[6],
                ),
            )
            for r in rows
        ]

    def get_dbt_node_execution_history(
        self, unique_id: str, depth: int = 30,
    ) -> list[float]:
        """Return execution times newest-first for a specific node."""
        rows = self._query(
            f"SELECT nt.execution_time FROM {self._table('dbt_node_timings')} nt "  # noqa: S608
            f"JOIN {self._table('dbt_runs')} r ON nt.dbt_run_id = r.id "
            "WHERE nt.unique_id = :unique_id "
            "ORDER BY r.id DESC LIMIT :depth",
            {"unique_id": unique_id, "depth": depth},
        )
        return [r[0] for r in rows]

    def get_dbt_node_timing_timeseries(
        self, unique_id: str, limit: int = 30,
    ) -> list[tuple[str, float]]:
        """Return (created_at, execution_time) for a node, oldest first."""
        rows = self._query(
            f"SELECT r.created_at, nt.execution_time FROM {self._table('dbt_node_timings')} nt "  # noqa: S608
            f"JOIN {self._table('dbt_runs')} r ON nt.dbt_run_id = r.id "
            "WHERE nt.unique_id = :unique_id "
            "ORDER BY r.id ASC LIMIT :limit",
            {"unique_id": unique_id, "limit": limit},
        )
        return [(r[0], r[1]) for r in rows]
