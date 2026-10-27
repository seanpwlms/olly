"""Findings and dispositions state mixin."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from olly.lifecycle import PriorFinding, apply_lifecycle
from olly.models import Disposition, Finding, FindingStatus

logger = logging.getLogger(__name__)


class FindingsStateMixin:
    """Methods for storing and querying findings and dispositions.

    Mixed into BaseStateStore — relies on _query, _execute,
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

    _FINDING_SELECT = (
        "SELECT id, connection_name, check_type, severity, "
        "schema_name, table_name, description, details, created_at"
    )

    _DISPOSITION_COLS = ("id", "finding_id", "disposition", "comment", "created_at", "created_by")

    # --- Findings ---

    def get_last_check_time(self) -> str | None:
        """Return the most recent created_at from the findings table, or None."""
        row = self._query_one(
            f"SELECT MAX(created_at) FROM {self._table('findings')}"
        )
        return row[0] if row and row[0] else None

    def store_findings(
        self, findings: list[Finding], created_at: str | None = None
    ) -> None:
        if not findings:
            return
        now = created_at or datetime.now(timezone.utc).isoformat()
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
                f.fingerprint,
            )
            for f in findings
        ]
        self._execute_many(
            f"INSERT INTO {self._table('findings')} "  # noqa: S608
            "(created_at, connection_name, check_type, severity, schema_name, "
            "table_name, description, details, fingerprint) "
            "VALUES (:created_at, :connection_name, :check_type, :severity, "
            ":schema_name, :table_name, :description, :details, :fingerprint)",
            ["created_at", "connection_name", "check_type", "severity",
             "schema_name", "table_name", "description", "details", "fingerprint"],
            rows,
        )
        logger.debug("Stored %d findings", len(findings))

    # --- Lifecycle ---

    def record_check_run(
        self, findings: list[Finding], scopes: set[tuple[str, str]]
    ) -> None:
        """Store a check run's findings, classifying each against the last run.

        Sets ``fingerprint``, ``status``, and ``id`` on each finding in
        place. Ongoing findings inherit their predecessor's disposition.

        Args:
            findings: Findings produced by this run.
            scopes: ``(connection_name, check_type)`` pairs that actually
                ran. A finding is compared only against the previous run of
                its own scope, so partial runs (``--select``,
                ``--connection``) don't make other findings look resolved.
        """
        now = datetime.now(timezone.utc).isoformat()
        previous = self._previous_findings(scopes)
        apply_lifecycle(findings, previous)
        self.store_findings(findings, created_at=now)
        if findings:
            self._assign_ids(findings, now)
            self._carry_over_dispositions(findings, previous)
        self._execute_many(
            f"INSERT INTO {self._table('check_runs')} "  # noqa: S608
            "(created_at, connection_name, check_type) "
            "VALUES (:created_at, :connection_name, :check_type)",
            ["created_at", "connection_name", "check_type"],
            [(now, conn, check) for conn, check in sorted(scopes)],
        )

    def _previous_findings(
        self, scopes: set[tuple[str, str]]
    ) -> dict[str, PriorFinding]:
        """Return findings from the last run of each scope, keyed by fingerprint."""
        if not scopes:
            return {}
        rows = self._query(
            "SELECT connection_name, check_type, MAX(created_at) "  # noqa: S608
            f"FROM {self._table('check_runs')} "
            "GROUP BY connection_name, check_type"
        )
        last_run = {(r[0], r[1]): r[2] for r in rows if (r[0], r[1]) in scopes}
        if not last_run:
            return {}

        times = sorted(set(last_run.values()))
        params = {f"t{i}": t for i, t in enumerate(times)}
        placeholders = ", ".join(f":{name}" for name in params)
        rows = self._query(
            "SELECT id, connection_name, check_type, severity, fingerprint, "  # noqa: S608
            f"created_at FROM {self._table('findings')} "
            f"WHERE created_at IN ({placeholders})",
            params,
        )
        return {
            fp: PriorFinding(id=fid, severity=severity)
            for fid, conn, check, severity, fp, created_at in rows
            if fp and last_run.get((conn, check)) == created_at
        }

    def _assign_ids(self, findings: list[Finding], created_at: str) -> None:
        """Copy stored row IDs back onto the in-memory findings."""
        rows = self._query(
            f"SELECT id, fingerprint FROM {self._table('findings')} "  # noqa: S608
            "WHERE created_at = :created_at",
            {"created_at": created_at},
        )
        ids = {fp: fid for fid, fp in rows}
        for f in findings:
            f.id = ids.get(f.fingerprint)

    def _carry_over_dispositions(
        self, findings: list[Finding], previous: dict[str, PriorFinding]
    ) -> None:
        """Copy dispositions from last run onto ongoing findings.

        Escalated findings start fresh so they get triaged again.
        """
        ongoing = [
            f for f in findings
            if f.status == FindingStatus.ONGOING.value and f.id is not None
        ]
        if not ongoing:
            return
        prior_ids = [previous[f.fingerprint].id for f in ongoing]
        dispositions = self.get_current_dispositions(prior_ids)
        for f, prior_id in zip(ongoing, prior_ids):
            disposition = dispositions.get(prior_id)
            if disposition is None or disposition == Disposition.NOT_STARTED.value:
                continue
            assert f.id is not None
            self.set_disposition(
                f.id, disposition,
                comment=f"Carried over from finding #{prior_id}",
                created_by="olly",
            )
            f.disposition = disposition

    def get_latest_findings(self, connection_name: str | None = None) -> list[Finding]:
        """Return findings from the most recent check run only."""
        last_check = self.get_last_check_time()
        if not last_check:
            return []
        t = self._table("findings")
        params: dict[str, Any] = {"created_at": last_check}
        where = "WHERE created_at = :created_at"
        if connection_name is not None:
            where += " AND connection_name = :connection_name"
            params["connection_name"] = connection_name
        rows = self._query(f"{self._FINDING_SELECT} FROM {t} {where}", params)  # noqa: S608
        return self._rows_to_findings(rows)

    def get_findings_history(self, limit: int = 100, connection_name: str | None = None) -> list[Finding]:
        t = self._table("findings")
        params: dict[str, Any] = {"limit": limit}
        where = ""
        if connection_name is not None:
            where = "WHERE connection_name = :connection_name "
            params["connection_name"] = connection_name
        rows = self._query(
            f"{self._FINDING_SELECT} FROM {t} {where}ORDER BY created_at DESC LIMIT :limit",  # noqa: S608
            params,
        )
        return self._rows_to_findings(rows)

    def _rows_to_findings(self, rows: list[tuple]) -> list[Finding]:
        return [
            Finding(id=r[0], connection_name=r[1], check_type=r[2], severity=r[3],
                    schema_name=r[4], table_name=r[5], description=r[6],
                    details=json.loads(r[7]) if r[7] else {},
                    created_at=r[8] if len(r) > 8 and r[8] else "")
            for r in rows
        ]

    # --- Dispositions ---

    def set_disposition(
        self, finding_id: int, disposition: str,
        comment: str = "", created_by: str = "",
    ) -> int:
        """Record a disposition change. Returns the disposition event ID."""
        valid = {d.value for d in Disposition}
        if disposition not in valid:
            msg = f"Invalid disposition {disposition!r}, must be one of {valid}"
            raise ValueError(msg)
        now = datetime.now(timezone.utc).isoformat()
        lastrowid = self._execute(
            f"INSERT INTO {self._table('finding_dispositions')} "  # noqa: S608
            "(finding_id, disposition, comment, created_at, created_by) "
            "VALUES (:finding_id, :disposition, :comment, :created_at, :created_by)",
            {"finding_id": finding_id, "disposition": disposition,
             "comment": comment, "created_at": now, "created_by": created_by},
        )
        assert lastrowid is not None
        return lastrowid

    def get_current_dispositions(self, finding_ids: list[int]) -> dict[int, str]:
        """Return {finding_id: disposition} for the latest disposition per finding."""
        if not finding_ids:
            return {}
        ids_csv = ", ".join(str(fid) for fid in finding_ids)
        t = self._table("finding_dispositions")
        rows = self._query(
            f"SELECT d.finding_id, d.disposition FROM {t} d "  # noqa: S608
            f"INNER JOIN (SELECT finding_id, MAX(id) AS max_id FROM {t} "
            f"WHERE finding_id IN ({ids_csv}) GROUP BY finding_id) "
            "latest ON d.id = latest.max_id",
        )
        return {r[0]: r[1] for r in rows}

    def get_disposition_history(self, finding_id: int) -> list[dict]:
        """Return disposition change history for a finding, newest first."""
        rows = self._query(
            f"SELECT id, finding_id, disposition, comment, created_at, created_by "  # noqa: S608
            f"FROM {self._table('finding_dispositions')} "
            "WHERE finding_id = :finding_id ORDER BY id DESC",
            {"finding_id": finding_id},
        )
        return [dict(zip(self._DISPOSITION_COLS, r)) for r in rows]
