from __future__ import annotations

import json
import logging
import time
from typing import Any


class _JsonlFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "sql": record.getMessage(),
        }
        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        return json.dumps(data)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat()


def setup_logging(verbose: bool = False) -> None:
    """Configure the ``olly`` logger hierarchy.

    Args:
        verbose: When True, set level to DEBUG; otherwise WARNING.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root = logging.getLogger("olly")
    root.setLevel(level)
    root.addHandler(handler)
    logging.getLogger("olly.queries").propagate = False


def setup_query_logging() -> None:
    """Configure the ``olly.queries`` logger to write JSONL to ``~/.olly/queries.jsonl``.

    Each line is a JSON object with ``timestamp``, ``sql``, and ``duration_ms`` fields.
    The logger does not propagate to the root ``olly`` logger so query lines stay
    out of stderr.
    """
    from olly.state.sqlite import get_olly_dir

    query_logger = logging.getLogger("olly.queries")
    # Avoid adding duplicate handlers if called multiple times
    if query_logger.handlers:
        return
    query_logger.setLevel(logging.DEBUG)
    query_logger.propagate = False

    log_path = get_olly_dir() / "queries.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(_JsonlFormatter())
    query_logger.addHandler(file_handler)


def log_query(sql: str, duration_ms: float) -> None:
    """Log a query to the ``olly.queries`` logger with timing metadata."""
    query_logger = logging.getLogger("olly.queries")
    query_logger.info(sql, extra={"duration_ms": round(duration_ms, 3)})


def timed_raw_sql(conn: Any, sql: str) -> Any:
    """Execute ``conn.raw_sql(sql)`` and log to the query logger with timing."""
    start = time.perf_counter()
    result = conn.raw_sql(sql)
    elapsed_ms = (time.perf_counter() - start) * 1000
    log_query(sql, elapsed_ms)
    return result
