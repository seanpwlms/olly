"""Tests for the --select flag on olly check."""

from __future__ import annotations

import json

import duckdb
import pytest

from olly.checker import run_checks
from olly.cli.check import ALL_CHECK_TYPES, _parse_select
from olly.cli.snapshot import take_snapshot
from olly.config import (
    ConnectionConfig,
    DbtConfig,
    NamedConnection,
    OllyConfig,
    Selection,
    Settings,
    write_config,
)


# --- _parse_select unit tests ---


def test_select_parses_valid_types():
    result = _parse_select("schema,volume")
    assert result == {"schema", "volume"}


def test_select_parses_single_type():
    result = _parse_select("dbt")
    assert result == {"dbt"}


def test_select_parses_all_types():
    result = _parse_select(",".join(ALL_CHECK_TYPES))
    assert result == ALL_CHECK_TYPES


def test_select_none_returns_none():
    assert _parse_select(None) is None


def test_select_strips_whitespace():
    result = _parse_select(" schema , volume ")
    assert result == {"schema", "volume"}


def test_select_rejects_invalid_types():
    with pytest.raises(SystemExit):
        _parse_select("schema,bogus")


def test_select_rejects_all_invalid():
    with pytest.raises(SystemExit):
        _parse_select("foo,bar")


# --- Integration tests with run_checks ---


def _setup_warehouse(tmp_path, monkeypatch):
    """Create a DuckDB warehouse, config, and two snapshots (with drift)."""
    db_path = tmp_path / "warehouse.duckdb"
    config_path = tmp_path / "olly.toml"

    raw = duckdb.connect(str(db_path))
    raw.execute("CREATE TABLE orders (id INT NOT NULL, amount DOUBLE NOT NULL)")
    raw.execute("INSERT INTO orders VALUES (1, 99.99), (2, 49.50)")
    raw.close()

    conn = ConnectionConfig(type="duckdb", path=str(db_path))
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(connections={"primary": nc}, settings=Settings())
    write_config(config, config_path)
    monkeypatch.chdir(tmp_path)

    # First snapshot (baseline)
    take_snapshot(config)

    # Introduce schema drift
    raw = duckdb.connect(str(db_path))
    raw.execute("ALTER TABLE orders ADD COLUMN new_col VARCHAR")
    raw.close()

    # Second snapshot (with drift)
    take_snapshot(config)

    return config


def test_select_dbt_only_skips_warehouse_checks(tmp_path):
    """When --select dbt, no connections are resolved and only dbt runs."""
    run_results = {
        "metadata": {"dbt_version": "1.0.0", "generated_at": "2024-01-01T00:00:00Z"},
        "results": [
            {
                "unique_id": "model.my_project.orders",
                "status": "error",
                "message": "Compilation Error",
                "execution_time": 1.5,
                "adapter_response": {},
            },
        ],
    }
    results_path = tmp_path / "run_results.json"
    results_path.write_text(json.dumps(run_results))

    config = OllyConfig(
        connections={},
        settings=Settings(),
        dbt=DbtConfig(run_results_path=str(results_path)),
    )
    findings, dbt_findings, cost_records = run_checks(
        config, select_checks={"dbt"},
    )
    assert findings == []
    assert cost_records == []
    assert len(dbt_findings) >= 1
    assert any(f.severity == "error" for f in dbt_findings)


def test_select_schema_only(tmp_path, monkeypatch):
    """When --select schema, only schema findings are returned."""
    config = _setup_warehouse(tmp_path, monkeypatch)

    findings, dbt_findings, cost_records = run_checks(
        config, select_checks={"schema"},
    )
    assert len(findings) > 0
    assert all(f.check_type == "schema" for f in findings)
    assert dbt_findings == []


def test_select_multiple(tmp_path, monkeypatch):
    """When --select schema,volume, both types run but others are skipped."""
    config = _setup_warehouse(tmp_path, monkeypatch)

    findings, dbt_findings, cost_records = run_checks(
        config, select_checks={"schema", "volume"},
    )
    check_types = {f.check_type for f in findings}
    assert check_types <= {"schema", "volume"}
    # Schema drift was introduced so we should get schema findings
    assert "schema" in check_types
    assert "freshness" not in check_types


def test_select_none_runs_all(tmp_path, monkeypatch):
    """When select_checks is None, all check types can produce findings."""
    config = _setup_warehouse(tmp_path, monkeypatch)

    findings, dbt_findings, cost_records = run_checks(
        config, select_checks=None,
    )
    assert isinstance(findings, list)
    assert isinstance(dbt_findings, list)
    # Schema drift exists, so we should get schema findings
    assert any(f.check_type == "schema" for f in findings)
