"""Dashboard-specific state queries.

These queries are only used by the dashboard and don't belong on BaseStateStore.
They access the protected _query/_table API intentionally — this module is the
single place where that boundary is crossed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from olly.state import BaseStateStore


def get_snapshot_history(
    state_db: BaseStateStore, days: int, connection_name: str = "",
) -> list[tuple[int, str, str, int]]:
    """Return recent snapshots as (id, created_at, connection_name, table_count)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    s = state_db._table("snapshots")  # noqa: SLF001
    ss = state_db._table("schema_snapshot")  # noqa: SLF001
    return state_db._query(  # noqa: SLF001
        f"SELECT s.id, s.created_at, s.connection_name, "  # noqa: S608
        f"COUNT(DISTINCT ss.schema_name || '.' || ss.table_name) "
        f"FROM {s} s LEFT JOIN {ss} ss ON ss.snapshot_id = s.id "
        f"WHERE s.created_at >= :cutoff AND s.connection_name = :connection_name "
        f"GROUP BY s.id ORDER BY s.id DESC",
        {"cutoff": cutoff, "connection_name": connection_name},
    )


def get_findings_trend(
    state_db: BaseStateStore, limit: int = 20,
) -> list[tuple[str, int, int]]:
    """Return (day, errors, warnings) per day, using the latest run each day."""
    t = state_db._table("findings")  # noqa: SLF001
    return state_db._query(  # noqa: SLF001
        "SELECT day, errors, warnings FROM ("  # noqa: S608
        "SELECT SUBSTR(created_at, 1, 10) AS day, "
        "SUM(CASE WHEN severity='error' THEN 1 ELSE 0 END) AS errors, "
        "SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) AS warnings, "
        "ROW_NUMBER() OVER (PARTITION BY SUBSTR(created_at, 1, 10) "
        "ORDER BY created_at DESC) AS rn "
        f"FROM {t} GROUP BY created_at"
        ") WHERE rn = 1 ORDER BY day DESC LIMIT :limit",
        {"limit": limit},
    )


def get_previous_finding_counts(
    state_db: BaseStateStore,
) -> tuple[int, int] | None:
    """Return (errors, warnings) from the second-most-recent check run."""
    t = state_db._table("findings")  # noqa: SLF001
    rows = state_db._query(  # noqa: SLF001
        f"SELECT DISTINCT created_at FROM {t} "  # noqa: S608
        "ORDER BY created_at DESC LIMIT 2",
    )
    if len(rows) < 2:
        return None
    row = state_db._query_one(  # noqa: SLF001
        f"SELECT SUM(CASE WHEN severity='error' THEN 1 ELSE 0 END), "  # noqa: S608
        f"SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) "
        f"FROM {t} WHERE created_at = :created_at",
        {"created_at": rows[1][0]},
    )
    return (row[0], row[1]) if row else None
