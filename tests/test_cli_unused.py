from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from olly.cli.unused import run_unused
from olly.config import (
    ConnectionConfig,
    NamedConnection,
    OllyConfig,
    Selection,
    Settings,
    UsageConfig,
    write_config,
)
from olly.models import UsageRecord


class FakeUsageAdapter:
    """Adapter that returns pre-configured usage records."""

    def __init__(self, records: list[UsageRecord]) -> None:
        self._records = records

    def list_schemas(self) -> list[str]:
        return ["public"]

    def fetch_table_usage(
        self,
        schemas: list[str],
        lookback_days: int,
        region: str = "us",
    ) -> list[UsageRecord]:
        return self._records


def _write_config(tmp_path):
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path="test.duckdb"),
        selection=Selection(include_schemas=["public"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
        usage=UsageConfig(enabled=True, lookback_days=90, unused_threshold_days=30),
    )
    write_config(config, tmp_path / "olly.toml")


def test_run_unused_with_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("public", "active", now - timedelta(days=1)),
        UsageRecord("public", "dead_table", None),
    ]

    with patch(
        "olly.cli.unused.connect_typed", return_value=FakeUsageAdapter(records)
    ):
        run_unused()

    output = capsys.readouterr().out
    assert "dead_table" in output
    assert "1 error(s)" in output


def test_run_unused_no_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    now = datetime.now(timezone.utc)
    records = [UsageRecord("public", "active", now - timedelta(days=1))]

    with patch(
        "olly.cli.unused.connect_typed", return_value=FakeUsageAdapter(records)
    ):
        run_unused()

    output = capsys.readouterr().out
    assert "No unused or stale tables found" in output


def test_run_unused_json_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    records = [UsageRecord("public", "dead_table", None)]

    with patch(
        "olly.cli.unused.connect_typed", return_value=FakeUsageAdapter(records)
    ):
        run_unused(output_json=True)

    output = capsys.readouterr().out
    assert '"findings"' in output
    assert "dead_table" in output
