from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from olly.models import ColumnInfo, CostRecord, TableInfo, VolumeRecord

if TYPE_CHECKING:
    from olly.config import OllyConfig

logger = logging.getLogger(__name__)


def get_olly_dir(project_root: Path | None = None) -> Path:
    """Compute the olly state directory path for the current project.

    Returns ``~/.olly/<project-hash>/`` where the hash is based on the
    absolute path of the project root.

    Args:
        project_root: Project root directory. If None, searches for olly.toml
            starting from the current directory.

    Returns:
        Path to the project-specific olly state directory.
    """
    if project_root is None:
        # Search for olly.toml starting from current directory
        cwd = Path.cwd()
        current = cwd
        while True:
            if (current / "olly.toml").exists():
                project_root = current
                break
            if current.parent == current:
                # Reached filesystem root without finding olly.toml
                # Fall back to current directory
                project_root = cwd
                break
            current = current.parent

    # Create a hash of the absolute project path
    abs_path = project_root.resolve()
    path_hash = hashlib.sha256(str(abs_path).encode()).hexdigest()[:16]

    # Return ~/.olly/<hash>/
    return Path.home() / ".olly" / path_hash


# Removed module-level constants to support test isolation
# Use get_olly_dir() at runtime instead

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

CREATE TABLE IF NOT EXISTS cost_snapshot (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    user_email TEXT NOT NULL,
    total_bytes_billed INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    query_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schema_snapshot_sid ON schema_snapshot(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_volume_snapshot_sid ON volume_snapshot(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cost_snapshot_sid ON cost_snapshot(snapshot_id);
"""

_SNAPSHOT_TABLES = ("schema_snapshot", "volume_snapshot", "cost_snapshot")


class StateDB:
    """SQLite-backed store for olly snapshot history.

    Manages schema and volume snapshots in ``~/.olly/<project-hash>/state.db``,
    providing methods to create, query, and prune historical snapshots.
    """

    def __init__(self, db_path: Path | None = None):
        """Initialize the state database connection.

        Args:
            db_path: Path to the SQLite database file. Defaults to
                ``~/.olly/<project-hash>/state.db`` based on the project root.
        """
        if db_path is None:
            db_path = get_olly_dir() / "state.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def _init_db(self) -> None:
        """Create the state database schema (all tables use IF NOT EXISTS)."""
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        logger.debug("Initialized state database at %s", self.db_path)

    def _migrate(self) -> None:
        """Apply schema migrations for existing databases."""
        cols = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(snapshots)").fetchall()
        }
        if "connection_name" not in cols:
            self.conn.execute(
                "ALTER TABLE snapshots ADD COLUMN connection_name TEXT NOT NULL DEFAULT ''"
            )
            self.conn.commit()

    def init_db(self) -> None:
        """Create the state database schema. Alias kept for compatibility."""
        self._init_db()

    def create_snapshot(self, connection_name: str = "") -> int:
        """Create a new snapshot record and return its ID.

        Args:
            connection_name: Name of the connection this snapshot belongs to.

        Returns:
            The auto-incremented snapshot ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO snapshots (created_at, connection_name) VALUES (?, ?)",
            (now, connection_name),
        )
        self.conn.commit()
        assert cur.lastrowid is not None
        logger.debug("Created snapshot #%d", cur.lastrowid)
        return cur.lastrowid

    def store_schema_data(self, snapshot_id: int, tables: list[TableInfo]) -> None:
        """Persist schema information for a snapshot.

        Args:
            snapshot_id: The snapshot to associate the data with.
            tables: Table metadata including columns to store.
        """
        rows = []
        for t in tables:
            for c in t.columns:
                rows.append(
                    (
                        snapshot_id,
                        t.schema_name,
                        t.table_name,
                        t.table_type,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                    )
                )
        self.conn.executemany(
            "INSERT INTO schema_snapshot "
            "(snapshot_id, schema_name, table_name, table_type, column_name, data_type, is_nullable) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def store_volume_data(self, snapshot_id: int, volumes: list[VolumeRecord]) -> None:
        """Persist row-count volume data for a snapshot.

        Args:
            snapshot_id: The snapshot to associate the data with.
            volumes: Volume records to store.
        """
        rows = [
            (snapshot_id, v.schema_name, v.table_name, v.row_count) for v in volumes
        ]
        self.conn.executemany(
            "INSERT INTO volume_snapshot (snapshot_id, schema_name, table_name, row_count) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def _get_latest_snapshot_id(self, connection_name: str = "") -> int | None:
        """Return the ID of the most recent snapshot, or ``None``."""
        row = self.conn.execute(
            "SELECT id FROM snapshots WHERE connection_name = ? ORDER BY id DESC LIMIT 1",
            (connection_name,),
        ).fetchone()
        return row[0] if row is not None else None

    def get_latest_schema(self, connection_name: str = "") -> list[TableInfo]:
        """Return schema data from the most recent snapshot.

        Returns:
            List of ``TableInfo`` objects, or an empty list if no snapshots exist.
        """
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_schema_for_snapshot(snapshot_id)

    def get_latest_volume(self, connection_name: str = "") -> list[VolumeRecord]:
        """Return volume data from the most recent snapshot.

        Returns:
            List of ``VolumeRecord`` objects, or an empty list if no snapshots exist.
        """
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self._load_volume_for_snapshot(snapshot_id)

    def get_latest_cost(self, connection_name: str = "") -> list[CostRecord]:
        """Return cost data from the most recent snapshot.

        Returns:
            List of ``CostRecord`` objects, or an empty list if no snapshots exist.
        """
        snapshot_id = self._get_latest_snapshot_id(connection_name)
        if snapshot_id is None:
            return []
        return self.get_cost_records_for_snapshot(snapshot_id)

    def _load_schema_for_snapshot(self, snapshot_id: int) -> list[TableInfo]:
        """Load and reconstruct TableInfo objects for a given snapshot.

        Args:
            snapshot_id: The snapshot whose schema data to load.

        Returns:
            List of ``TableInfo`` objects with populated column lists.
        """
        rows = self.conn.execute(
            "SELECT schema_name, table_name, table_type, column_name, data_type, is_nullable "
            "FROM schema_snapshot WHERE snapshot_id = ? "
            "ORDER BY schema_name, table_name, column_name",
            (snapshot_id,),
        ).fetchall()

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

    def _load_volume_for_snapshot(self, snapshot_id: int) -> list[VolumeRecord]:
        """Load volume records for a given snapshot.

        Args:
            snapshot_id: The snapshot whose volume data to load.

        Returns:
            List of ``VolumeRecord`` objects.
        """
        rows = self.conn.execute(
            "SELECT schema_name, table_name, row_count "
            "FROM volume_snapshot WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        return [
            VolumeRecord(schema_name=r[0], table_name=r[1], row_count=r[2])
            for r in rows
        ]

    def get_volume_history(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> list[int]:
        """Return recent row counts for a table, newest first.

        Args:
            schema_name: Schema containing the table.
            table_name: Name of the table.
            depth: Maximum number of historical counts to return.
            connection_name: Connection to filter by.

        Returns:
            List of row counts ordered most-recent first.
        """
        rows = self.conn.execute(
            "SELECT v.row_count FROM volume_snapshot v "
            "JOIN snapshots s ON v.snapshot_id = s.id "
            "WHERE v.schema_name = ? AND v.table_name = ? "
            "AND s.connection_name = ? "
            "ORDER BY s.id DESC LIMIT ?",
            (schema_name, table_name, connection_name, depth),
        ).fetchall()
        return [r[0] for r in rows]

    def get_recent_volume_unchanged_count(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> int:
        """Return the number of most recent consecutive snapshots with the same row count.

        Args:
            schema_name: Schema containing the table.
            table_name: Name of the table.
            depth: Maximum number of historical snapshots to inspect.

        Returns:
            Count of consecutive latest snapshots sharing the same row count,
            or 0 if fewer than two snapshots exist.
        """
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

    def prune_old_snapshots(self, keep: int, connection_name: str = "") -> None:
        """Delete the oldest snapshots, retaining only the most recent ones.

        Args:
            keep: Number of most recent snapshots to retain.
        """
        row = self.conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE connection_name = ?",
            (connection_name,),
        ).fetchone()
        total = row[0] if row else 0
        if total <= keep:
            return
        logger.debug("Pruning snapshots older than depth %d", keep)
        rows = self.conn.execute(
            "SELECT id FROM snapshots WHERE connection_name = ? ORDER BY id ASC LIMIT ?",
            (connection_name, total - keep),
        ).fetchall()
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        for table in _SNAPSHOT_TABLES:
            self.conn.execute(
                f"DELETE FROM {table} WHERE snapshot_id IN ({placeholders})",  # noqa: S608
                ids,
            )
        self.conn.execute(
            f"DELETE FROM snapshots WHERE id IN ({placeholders})",  # noqa: S608
            ids,
        )
        self.conn.commit()

    def store_cost_data(self, snapshot_id: int, records: list[CostRecord]) -> None:
        """Persist cost records for a snapshot.

        Args:
            snapshot_id: The snapshot to associate the data with.
            records: Cost records to store.
        """
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
        self.conn.executemany(
            "INSERT INTO cost_snapshot "
            "(snapshot_id, schema_name, table_name, user_email, "
            "total_bytes_billed, estimated_cost_usd, query_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def get_cost_history(
        self, depth: int, connection_name: str = ""
    ) -> list[tuple[int, float]]:
        """Return recent per-snapshot total costs, newest first.

        Args:
            depth: Maximum number of historical snapshots to return.
            connection_name: Connection to filter by.

        Returns:
            List of (snapshot_id, total_estimated_cost_usd) tuples.
        """
        rows = self.conn.execute(
            "SELECT c.snapshot_id, SUM(c.estimated_cost_usd) AS total_cost "
            "FROM cost_snapshot c "
            "JOIN snapshots s ON c.snapshot_id = s.id "
            "WHERE s.connection_name = ? "
            "GROUP BY c.snapshot_id "
            "ORDER BY s.id DESC LIMIT ?",
            (connection_name, depth),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_cost_records_for_snapshot(self, snapshot_id: int) -> list[CostRecord]:
        """Load cost records for a given snapshot.

        Args:
            snapshot_id: The snapshot whose cost data to load.

        Returns:
            List of ``CostRecord`` objects.
        """
        rows = self.conn.execute(
            "SELECT schema_name, table_name, user_email, "
            "total_bytes_billed, estimated_cost_usd, query_count "
            "FROM cost_snapshot WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
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

    def get_volume_timeseries(
        self, schema_name: str, table_name: str, depth: int = 30,
        connection_name: str = "",
    ) -> list[tuple[str, int]]:
        """Return ``(created_at, row_count)`` pairs for charting, oldest first."""
        rows = self.conn.execute(
            "SELECT s.created_at, v.row_count FROM volume_snapshot v "
            "JOIN snapshots s ON v.snapshot_id = s.id "
            "WHERE v.schema_name = ? AND v.table_name = ? "
            "AND s.connection_name = ? "
            "ORDER BY s.id ASC LIMIT ?",
            (schema_name, table_name, connection_name, depth),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def get_table_first_seen(
        self, schema_name: str, table_name: str,
        connection_name: str = "",
    ) -> tuple[str | None, int]:
        """Return ``(first_seen_str, snapshot_count)`` for a table."""
        row = self.conn.execute(
            "SELECT MIN(s.created_at), COUNT(DISTINCT s.id) "
            "FROM schema_snapshot ss "
            "JOIN snapshots s ON ss.snapshot_id = s.id "
            "WHERE ss.schema_name = ? AND ss.table_name = ? "
            "AND s.connection_name = ?",
            (schema_name, table_name, connection_name),
        ).fetchone()

        if not row or row[0] is None:
            return None, 0
        return row[0], row[1]

    def get_recent_snapshot_ids_for_table(
        self, schema_name: str, table_name: str, limit: int = 2,
        connection_name: str = "",
    ) -> list[int]:
        """Return the most recent snapshot IDs containing this table, newest first."""
        rows = self.conn.execute(
            "SELECT DISTINCT s.id FROM schema_snapshot ss "
            "JOIN snapshots s ON ss.snapshot_id = s.id "
            "WHERE ss.schema_name = ? AND ss.table_name = ? "
            "AND s.connection_name = ? "
            "ORDER BY s.id DESC LIMIT ?",
            (schema_name, table_name, connection_name, limit),
        ).fetchall()
        return [r[0] for r in rows]

    def get_columns_for_snapshot(
        self, snapshot_id: int, schema_name: str, table_name: str
    ) -> dict[str, tuple[str, bool]]:
        """Return ``{column_name: (data_type, is_nullable)}`` for a snapshot."""
        rows = self.conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM schema_snapshot "
            "WHERE snapshot_id = ? AND schema_name = ? AND table_name = ?",
            (snapshot_id, schema_name, table_name),
        ).fetchall()
        return {r[0]: (r[1], bool(r[2])) for r in rows}

    def has_snapshots(self, connection_name: str = "") -> bool:
        """Return True if at least one snapshot exists."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE connection_name = ?",
            (connection_name,),
        ).fetchone()
        return bool(row and row[0] > 0)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> StateDB:
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        self.close()


class StateStore(Protocol):
    """Protocol for snapshot state storage backends."""

    def create_snapshot(self, connection_name: str = "") -> int: ...
    def store_schema_data(self, snapshot_id: int, tables: list[TableInfo]) -> None: ...
    def store_volume_data(
        self, snapshot_id: int, volumes: list[VolumeRecord]
    ) -> None: ...
    def get_latest_schema(self, connection_name: str = "") -> list[TableInfo]: ...
    def get_latest_volume(self, connection_name: str = "") -> list[VolumeRecord]: ...
    def get_latest_cost(self, connection_name: str = "") -> list[CostRecord]: ...
    def get_volume_history(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> list[int]: ...
    def get_recent_volume_unchanged_count(
        self, schema_name: str, table_name: str, depth: int,
        connection_name: str = "",
    ) -> int: ...
    def prune_old_snapshots(self, keep: int, connection_name: str = "") -> None: ...
    def store_cost_data(self, snapshot_id: int, records: list[CostRecord]) -> None: ...
    def get_cost_history(
        self, depth: int, connection_name: str = ""
    ) -> list[tuple[int, float]]: ...
    def get_cost_records_for_snapshot(self, snapshot_id: int) -> list[CostRecord]: ...
    def get_volume_timeseries(
        self, schema_name: str, table_name: str, depth: int = 30,
        connection_name: str = "",
    ) -> list[tuple[str, int]]: ...
    def get_table_first_seen(
        self, schema_name: str, table_name: str,
        connection_name: str = "",
    ) -> tuple[str | None, int]: ...
    def get_recent_snapshot_ids_for_table(
        self, schema_name: str, table_name: str, limit: int = 2,
        connection_name: str = "",
    ) -> list[int]: ...
    def get_columns_for_snapshot(
        self, snapshot_id: int, schema_name: str, table_name: str
    ) -> dict[str, tuple[str, bool]]: ...
    def has_snapshots(self, connection_name: str = "") -> bool: ...
    def close(self) -> None: ...
    def __enter__(self) -> StateStore: ...
    def __exit__(
        self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object
    ) -> None: ...


def open_state(
    config: OllyConfig, adapter: Any = None, conn_type: str = ""
) -> StateStore:
    """Create a state store based on configuration.

    When ``state_schema`` is set and an adapter is provided, state is stored
    in the warehouse. Otherwise falls back to local SQLite.

    Args:
        config: Olly configuration.
        adapter: Optional adapter instance (needed for warehouse state).
        conn_type: Connection type string (e.g. "duckdb"). Used for
            warehouse state dialect selection.
    """
    if config.settings.state_schema and adapter is not None:
        from olly.warehouse_state import WarehouseStateStore

        return WarehouseStateStore(
            adapter.backend, config.settings.state_schema, conn_type
        )
    return StateDB()
