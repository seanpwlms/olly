from unittest.mock import patch

import duckdb
import pytest

from olly.cli.check import (
    print_cost_summary,
    print_dbt_findings_table,
    print_findings_json,
    print_findings_table,
    run_check,
    run_checks,
)
from olly.cli.config_explain import run_config_explain
from olly.cli.init import run_init
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
from olly.models import CostRecord, DbtFinding, Finding
from olly.state import get_olly_dir


def _write_config(path, duckdb_path):
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path=str(duckdb_path)),
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
    )
    write_config(config, path)
    return config


def test_run_snapshot_and_check(tmp_path, monkeypatch, duckdb_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "olly.toml"
    config = _write_config(config_path, duckdb_path)

    take_snapshot(config)
    run_check(output_json=True, write_results=False)


def test_run_config_explain(tmp_path, monkeypatch, duckdb_path, capsys):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "olly.toml"
    _write_config(config_path, duckdb_path)

    run_config_explain()
    output = capsys.readouterr().out
    assert "Config explain" in output


def test_run_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "init.duckdb"
    duckdb.connect(str(db_path)).close()

    responses = iter(["duckdb", str(db_path)])
    monkeypatch.setattr(
        "olly.cli.init.console.input",
        lambda _: next(responses),
    )

    run_init()

    assert (tmp_path / "olly.toml").exists()
    assert (get_olly_dir(tmp_path) / "state.db").exists()


# --- run_check CLI entry point tests ---


def test_run_check_no_snapshots(tmp_path, monkeypatch, duckdb_path):
    """No snapshots -> SystemExit(1) with message."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "olly.toml", duckdb_path)

    with pytest.raises(SystemExit):
        run_check(write_results=False)


def test_run_check_table_output_no_findings(tmp_path, monkeypatch, duckdb_path, capsys):
    """Table output mode, no findings -> 'All checks passed'."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    run_check(output_json=False, write_results=False)
    output = capsys.readouterr().out
    assert "All checks passed" in output


def test_run_check_table_output_with_findings(
    tmp_path, monkeypatch, duckdb_path, capsys
):
    """Table output mode with findings -> prints table + summary + exits 1."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    fake_finding = Finding(
        check_type="schema",
        severity="error",
        schema_name="main",
        table_name="orders",
        description="Column dropped",
    )
    with patch("olly.cli.check.run_checks", return_value=([fake_finding], [], [])):
        with pytest.raises(SystemExit):
            run_check(output_json=False, write_results=False)
    output = capsys.readouterr().out
    assert "1 error(s)" in output


def test_run_check_write_results(tmp_path, monkeypatch, duckdb_path):
    """write_results=True -> calls write_findings_json."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    run_check(output_json=True, write_results=True)
    assert (get_olly_dir(tmp_path) / "findings.json").exists()


def test_run_check_exit_code_1_with_findings(tmp_path, monkeypatch, duckdb_path):
    """Exit code 1 when findings are present."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    fake_finding = Finding(
        check_type="volume",
        severity="warning",
        schema_name="main",
        table_name="orders",
        description="Row count anomaly",
    )
    with patch("olly.cli.check.run_checks", return_value=([fake_finding], [], [])):
        with pytest.raises(SystemExit):
            run_check(output_json=True, write_results=False)


# --- Print function tests ---


def test_print_findings_table(capsys):
    findings = [
        Finding(
            check_type="schema",
            severity="error",
            schema_name="main",
            table_name="orders",
            description="Column dropped",
        ),
        Finding(
            check_type="volume",
            severity="warning",
            schema_name="main",
            table_name="customers",
            description="Row count anomaly",
        ),
    ]
    print_findings_table(findings)
    output = capsys.readouterr().out
    assert "Findings" in output
    assert "Column dropped" in output


def test_print_dbt_findings_table(capsys):
    dbt_findings = [
        DbtFinding(
            resource_type="model",
            severity="error",
            unique_id="model.project.orders",
            status="error",
            execution_time=12.5,
            description="Compilation error",
        ),
    ]
    print_dbt_findings_table(dbt_findings)
    output = capsys.readouterr().out
    assert "dbt Findings" in output
    assert "Compilation error" in output


def test_print_cost_summary(capsys):
    records = [
        CostRecord(
            schema_name="main",
            table_name="orders",
            user_email="alice@example.com",
            total_bytes_billed=1_000_000_000,
            estimated_cost_usd=5.0,
            query_count=10,
        ),
    ]
    print_cost_summary(records)
    output = capsys.readouterr().out
    assert "Cost" in output
    assert "$5.00" in output


def test_print_findings_json_with_cost(capsys):
    findings = [
        Finding(
            check_type="schema",
            severity="error",
            schema_name="main",
            table_name="orders",
            description="Column dropped",
        ),
    ]
    cost_records = [
        CostRecord(
            schema_name="main",
            table_name="orders",
            user_email="alice@example.com",
            total_bytes_billed=1_000_000_000,
            estimated_cost_usd=5.0,
            query_count=10,
        ),
    ]
    print_findings_json(findings, cost_records=cost_records)
    output = capsys.readouterr().out
    assert "cost_summary" in output


# --- _run_dbt_checks ---


def test_run_dbt_checks_relative_path(tmp_path, monkeypatch, duckdb_path):
    """Relative dbt path resolves relative to config_path."""
    monkeypatch.chdir(tmp_path)
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path=str(duckdb_path)),
        selection=Selection(include_schemas=["main"]),
    )
    config = OllyConfig(
        connections={"primary": nc},
        settings=Settings(),
        dbt=DbtConfig(run_results_path="target/run_results.json"),
        config_path=tmp_path / "olly.toml",
    )
    write_config(config, tmp_path / "olly.toml")
    take_snapshot(config)

    # run_checks will call _run_dbt_checks internally; the file won't exist
    # but this exercises the relative path resolution code path
    findings, dbt_findings, cost_records = run_checks(config)
    assert dbt_findings == []


def test_run_check_dbt_findings_summary(tmp_path, monkeypatch, duckdb_path, capsys):
    """dbt findings present -> prints dbt summary counts."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    dbt_finding = DbtFinding(
        resource_type="model",
        severity="error",
        unique_id="model.project.orders",
        status="error",
        execution_time=5.0,
        description="Compile error",
    )
    with patch("olly.cli.check.run_checks", return_value=([], [dbt_finding], [])):
        with pytest.raises(SystemExit):
            run_check(output_json=False, write_results=False)
    output = capsys.readouterr().out
    assert "1 dbt error(s)" in output


# --- Slack alerting integration ---


def test_run_check_calls_slack_alert(tmp_path, monkeypatch, duckdb_path):
    """send_slack_alert is called after run_checks completes."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    with patch("olly.cli.check.send_slack_alert") as mock_slack:
        run_check(output_json=True, write_results=False)
        mock_slack.assert_called_once()


def test_run_check_passes_findings_to_slack(tmp_path, monkeypatch, duckdb_path):
    """Findings from run_checks are forwarded to send_slack_alert."""
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path / "olly.toml", duckdb_path)
    take_snapshot(config)

    fake_finding = Finding(
        check_type="schema",
        severity="error",
        schema_name="main",
        table_name="orders",
        description="Column dropped",
    )
    with patch("olly.cli.check.run_checks", return_value=([fake_finding], [], [])):
        with patch("olly.cli.check.send_slack_alert") as mock_slack:
            with pytest.raises(SystemExit):
                run_check(output_json=True, write_results=False)
            args = mock_slack.call_args[0]
            # args: (config.slack, findings, dbt_findings)
            assert args[1] == [fake_finding]
            assert args[2] == []
