"""Tests for the ``olly create-state`` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from olly.cli.create_state import run_create_state
from olly.state.warehouse import WarehouseStateStore


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "olly.toml"
    p.write_text(content)
    return p


def test_no_state_schema_exits(tmp_path, monkeypatch):
    """Exits with error when state_schema is not configured."""
    _write_toml(
        tmp_path,
        '[connection]\ntype = "duckdb"\npath = "test.duckdb"\n',
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        run_create_state()


def test_lists_objects_and_creates_on_confirm(tmp_path, monkeypatch):
    """Lists objects and creates tables when user confirms."""
    db_path = tmp_path / "test.duckdb"
    _write_toml(
        tmp_path,
        (
            '[connection]\ntype = "duckdb"\n'
            f'path = "{db_path}"\n\n'
            "[settings]\n"
            'state_schema = "_olly_state"\n'
        ),
    )
    monkeypatch.chdir(tmp_path)

    output_lines: list[str] = []

    def fake_print(msg: str = "", **_kwargs):
        output_lines.append(str(msg))

    def fake_input(_prompt: str = "") -> str:
        return "y"

    with patch("olly.cli.create_state.console") as mock_console:
        mock_console.print = fake_print
        mock_console.input = fake_input
        run_create_state()

    combined = "\n".join(output_lines)
    # All table names should appear in the output
    for table_name in WarehouseStateStore.TABLE_NAMES:
        assert table_name in combined

    assert "_olly_state" in combined
    assert "created" in combined.lower()


def test_abort_on_decline(tmp_path, monkeypatch):
    """Exits cleanly when user declines."""
    db_path = tmp_path / "test.duckdb"
    _write_toml(
        tmp_path,
        (
            '[connection]\ntype = "duckdb"\n'
            f'path = "{db_path}"\n\n'
            "[settings]\n"
            'state_schema = "_olly_state"\n'
        ),
    )
    monkeypatch.chdir(tmp_path)

    def fake_input(_prompt: str = "") -> str:
        return "n"

    with patch("olly.cli.create_state.console") as mock_console:
        mock_console.print = lambda *a, **kw: None
        mock_console.input = fake_input
        with pytest.raises(SystemExit) as exc_info:
            run_create_state()
        assert exc_info.value.code == 0
