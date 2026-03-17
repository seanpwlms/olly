from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

from olly.config import Settings
from olly.logging import (
    _JsonlFormatter,
    log_query,
    setup_query_logging,
    timed_raw_sql,
)


class _ListHandler(logging.Handler):
    """A logging handler that collects records in a list."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestSetupQueryLogging:
    def test_creates_file_handler(self, tmp_path):
        # conftest patches get_olly_dir to tmp_path / ".olly"
        query_logger = logging.getLogger("olly.queries")
        query_logger.handlers.clear()

        setup_query_logging()

        assert len(query_logger.handlers) == 1
        handler = query_logger.handlers[0]
        assert isinstance(handler, logging.FileHandler)
        assert handler.baseFilename.endswith("queries.jsonl")
        assert query_logger.propagate is False

    def test_idempotent(self, tmp_path):
        query_logger = logging.getLogger("olly.queries")
        query_logger.handlers.clear()

        setup_query_logging()
        setup_query_logging()

        assert len(query_logger.handlers) == 1

    def test_creates_directory(self, tmp_path, monkeypatch):
        olly_dir = tmp_path / "nested" / ".olly"
        monkeypatch.setattr("olly.state.sqlite.get_olly_dir", lambda: olly_dir)
        query_logger = logging.getLogger("olly.queries")
        query_logger.handlers.clear()

        setup_query_logging()

        assert olly_dir.exists()


class TestJsonlFormatter:
    def test_format_produces_valid_json(self):
        formatter = _JsonlFormatter()
        record = logging.LogRecord(
            name="olly.queries",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="SELECT 1",
            args=None,
            exc_info=None,
        )
        record.duration_ms = 42.5
        line = formatter.format(record)
        data = json.loads(line)
        assert data["sql"] == "SELECT 1"
        assert data["duration_ms"] == 42.5
        assert "timestamp" in data

    def test_format_without_duration(self):
        formatter = _JsonlFormatter()
        record = logging.LogRecord(
            name="olly.queries",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="SELECT 1",
            args=None,
            exc_info=None,
        )
        line = formatter.format(record)
        data = json.loads(line)
        assert "duration_ms" not in data


class TestLogQuery:
    def test_log_query_sends_to_logger(self):
        query_logger = logging.getLogger("olly.queries")
        handler = _ListHandler()
        query_logger.handlers = [handler]
        query_logger.setLevel(logging.DEBUG)
        query_logger.propagate = False

        log_query("SELECT 1", 42.5)

        assert len(handler.records) == 1
        record = handler.records[0]
        assert record.getMessage() == "SELECT 1"
        assert record.duration_ms == 42.5  # type: ignore[attr-defined]


class TestTimedRawSql:
    def test_logs_and_returns_result(self):
        mock_conn = MagicMock()
        mock_conn.raw_sql.return_value = "result"

        query_logger = logging.getLogger("olly.queries")
        handler = _ListHandler()
        query_logger.handlers = [handler]
        query_logger.setLevel(logging.DEBUG)
        query_logger.propagate = False

        result = timed_raw_sql(mock_conn, "SELECT 1")

        assert result == "result"
        mock_conn.raw_sql.assert_called_once_with("SELECT 1")
        assert len(handler.records) == 1
        record = handler.records[0]
        assert record.getMessage() == "SELECT 1"
        assert hasattr(record, "duration_ms")
        assert record.duration_ms >= 0  # type: ignore[attr-defined]


class TestBaseAdapterRawSql:
    def test_raw_sql_logs_query(self, backend):
        """Verify _raw_sql on a real DuckDB adapter logs the query."""
        query_logger = logging.getLogger("olly.queries")
        handler = _ListHandler()
        original_handlers = query_logger.handlers[:]
        query_logger.handlers = [handler]
        query_logger.setLevel(logging.DEBUG)
        query_logger.propagate = False

        try:
            result = backend._raw_sql("SELECT 42 AS answer")
            row = result.fetchone()
            assert row[0] == 42
            assert len(handler.records) == 1
            assert "SELECT 42" in handler.records[0].getMessage()
        finally:
            query_logger.handlers = original_handlers


class TestConfigLogQueries:
    def test_default_false(self):
        settings = Settings()
        assert settings.log_queries is False

    def test_set_true(self):
        settings = Settings(log_queries=True)
        assert settings.log_queries is True

    def test_toml_parsing(self, tmp_path, monkeypatch):
        toml_content = """\
[connection]
type = "duckdb"
path = "test.duckdb"

[settings]
log_queries = true
"""
        config_path = tmp_path / "olly.toml"
        config_path.write_text(toml_content)
        monkeypatch.chdir(tmp_path)

        from olly.config import load_config

        config = load_config()
        assert config.settings.log_queries is True


class TestEndToEndJsonl:
    def test_queries_written_to_file(self, tmp_path, backend):
        """Full integration: setup logging, run a query, verify JSONL output."""
        # conftest patches get_olly_dir to tmp_path / ".olly"
        olly_dir = tmp_path / ".olly"
        query_logger = logging.getLogger("olly.queries")
        query_logger.handlers.clear()

        setup_query_logging()

        backend._raw_sql("SELECT 1 AS test_col")

        # Flush the handler
        for h in query_logger.handlers:
            h.flush()

        log_file = olly_dir / "queries.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["sql"] == "SELECT 1 AS test_col"
        assert "timestamp" in data
        assert "duration_ms" in data
        assert data["duration_ms"] >= 0
