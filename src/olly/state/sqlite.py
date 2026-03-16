"""SQLite-backed state store implementation."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from olly.state.base import BaseStateStore

logger = logging.getLogger(__name__)

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    connection_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schema_snapshot (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    table_type TEXT NOT NULL,
    column_name TEXT NOT NULL,
    data_type TEXT NOT NULL,
    is_nullable BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS volume_snapshot (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    connection_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cost_records (
    cost_run_id INTEGER NOT NULL REFERENCES cost_runs(id),
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    user_email TEXT NOT NULL,
    total_bytes_billed INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    query_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    connection_name TEXT NOT NULL,
    check_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    description TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dbt_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    unique_id TEXT NOT NULL,
    status TEXT NOT NULL,
    execution_time REAL NOT NULL,
    description TEXT NOT NULL,
    details TEXT NOT NULL,
    dbt_run_id INTEGER
);

CREATE TABLE IF NOT EXISTS finding_dispositions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES findings(id),
    disposition TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dbt_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    invocation_id TEXT NOT NULL,
    elapsed_time REAL NOT NULL,
    total_nodes INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    pass_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dbt_node_timings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dbt_run_id INTEGER NOT NULL REFERENCES dbt_runs(id),
    unique_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    execution_time REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schema_snapshot_sid ON schema_snapshot(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_volume_snapshot_sid ON volume_snapshot(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cost_records_run_id ON cost_records(cost_run_id);
CREATE INDEX IF NOT EXISTS idx_findings_created_at ON findings(created_at);
CREATE INDEX IF NOT EXISTS idx_findings_connection ON findings(connection_name);
CREATE INDEX IF NOT EXISTS idx_dbt_findings_created_at ON dbt_findings(created_at);
CREATE INDEX IF NOT EXISTS idx_finding_dispositions_fid ON finding_dispositions(finding_id);
CREATE INDEX IF NOT EXISTS idx_dbt_runs_created_at ON dbt_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_dbt_node_timings_run_id ON dbt_node_timings(dbt_run_id);
CREATE INDEX IF NOT EXISTS idx_dbt_node_timings_unique_id ON dbt_node_timings(unique_id);
"""

# Regex to convert :name placeholders to ? for sqlite3
_NAMED_PARAM_RE = re.compile(r":([a-zA-Z_]\w*)")


def _to_positional(sql: str, params: dict[str, Any] | None) -> tuple[str, tuple]:
    """Convert :name style SQL to ? style for sqlite3."""
    if params is None:
        return sql, ()
    ordered: list[Any] = []

    def replacer(m: re.Match) -> str:
        ordered.append(params[m.group(1)])
        return "?"

    converted = _NAMED_PARAM_RE.sub(replacer, sql)
    return converted, tuple(ordered)


def get_olly_dir() -> Path:
    """Return the olly state directory path (``~/.olly/``)."""
    return Path.home() / ".olly"


class StateDB(BaseStateStore):
    """SQLite-backed store for olly snapshot history.

    Manages schema and volume snapshots in ``~/.olly/<project-hash>/state.db``,
    providing methods to create, query, and prune historical snapshots.
    """

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = get_olly_dir() / "state.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        logger.debug("Initialized state database at %s", self.db_path)

    def init_db(self) -> None:
        """No-op kept for test compatibility. Tables are created in __init__."""
        self._init_tables()

    def _migrate(self) -> None:
        cols = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(snapshots)").fetchall()
        }
        if "connection_name" not in cols:
            self.conn.execute(
                "ALTER TABLE snapshots ADD COLUMN connection_name TEXT NOT NULL DEFAULT ''"
            )
            self.conn.commit()

        # Ensure finding_dispositions table exists for older databases
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "finding_dispositions" not in tables:
            self.conn.executescript(
                "CREATE TABLE IF NOT EXISTS finding_dispositions ("
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "    finding_id INTEGER NOT NULL REFERENCES findings(id),"
                "    disposition TEXT NOT NULL,"
                "    comment TEXT NOT NULL DEFAULT '',"
                "    created_at TEXT NOT NULL,"
                "    created_by TEXT NOT NULL DEFAULT ''"
                ");"
                "CREATE INDEX IF NOT EXISTS idx_finding_dispositions_fid "
                "ON finding_dispositions(finding_id);"
            )

        if "dbt_runs" not in tables:
            self.conn.executescript(
                "CREATE TABLE IF NOT EXISTS dbt_runs ("
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "    created_at TEXT NOT NULL,"
                "    invocation_id TEXT NOT NULL,"
                "    elapsed_time REAL NOT NULL,"
                "    total_nodes INTEGER NOT NULL,"
                "    error_count INTEGER NOT NULL,"
                "    warning_count INTEGER NOT NULL,"
                "    pass_count INTEGER NOT NULL"
                ");"
                "CREATE INDEX IF NOT EXISTS idx_dbt_runs_created_at ON dbt_runs(created_at);"
            )

        # Add dbt_run_id column to dbt_findings for existing databases
        if "dbt_findings" in tables:
            dbt_cols = {
                row[1]
                for row in self.conn.execute("PRAGMA table_info(dbt_findings)").fetchall()
            }
            if "dbt_run_id" not in dbt_cols:
                self.conn.execute(
                    "ALTER TABLE dbt_findings ADD COLUMN dbt_run_id INTEGER"
                )
                self.conn.commit()

        if "dbt_node_timings" not in tables:
            self.conn.executescript(
                "CREATE TABLE IF NOT EXISTS dbt_node_timings ("
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "    dbt_run_id INTEGER NOT NULL REFERENCES dbt_runs(id),"
                "    unique_id TEXT NOT NULL,"
                "    resource_type TEXT NOT NULL,"
                "    execution_time REAL NOT NULL,"
                "    status TEXT NOT NULL"
                ");"
                "CREATE INDEX IF NOT EXISTS idx_dbt_node_timings_run_id ON dbt_node_timings(dbt_run_id);"
                "CREATE INDEX IF NOT EXISTS idx_dbt_node_timings_unique_id ON dbt_node_timings(unique_id);"
            )

    def _table(self, name: str) -> str:
        return name

    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
        q, p = _to_positional(sql, params)
        return self.conn.execute(q, p).fetchall()

    def _execute(self, sql: str, params: dict[str, Any] | None = None) -> int | None:
        q, p = _to_positional(sql, params)
        cur = self.conn.execute(q, p)
        self.conn.commit()
        return cur.lastrowid

    def _execute_many(
        self, sql: str, column_names: list[str], rows: list[tuple]
    ) -> None:
        # For SQLite, convert :name to ? and build positional param tuples
        # We need to map each row tuple to positional params
        q, _ = _to_positional(sql, {name: None for name in column_names})
        self.conn.executemany(q, rows)
        self.conn.commit()

    def _delete_by_ids(self, table: str, column: str, ids: list[int]) -> None:
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"DELETE FROM {self._table(table)} WHERE {column} IN ({placeholders})",  # noqa: S608
            ids,
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def clean(self) -> None:
        """Delete the SQLite state database file."""
        self.close()
        if self.db_path.exists():
            self.db_path.unlink()
            logger.info("Deleted state database at %s", self.db_path)
