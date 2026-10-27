"""Tests for finding fingerprints, lifecycle status, and fail_on policy."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import duckdb
import ibis
import pytest

from olly.cli.check import should_fail
from olly.cli.snapshot import take_snapshot
from olly.checker import run_checks
from olly.config import SlackConfig
from olly.config_ops import validate_config
from olly.lifecycle import PriorFinding, apply_lifecycle, fingerprint, needs_attention
from olly.models import DbtFinding, FindingStatus
from olly.slack import send_slack_alert
from olly.state import StateDB, WarehouseStateStore
from conftest import make_config, make_finding

SCOPE = {("primary", "schema")}


def _schema_finding(severity="error", column="email", **details):
    return make_finding(
        "schema", severity,
        details={"change": "column_removed", "column": column, **details},
    )


# --- fingerprint ---


def test_fingerprint_ignores_measured_values():
    a = make_finding("volume", "warning", details={"direction": "increase", "z_score": 3.1})
    b = make_finding("volume", "error", details={"direction": "increase", "z_score": 9.0})
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_distinguishes_identity_keys():
    up = make_finding("volume", details={"direction": "increase"})
    down = make_finding("volume", details={"direction": "decrease"})
    assert fingerprint(up) != fingerprint(down)
    assert fingerprint(_schema_finding(column="a")) != fingerprint(_schema_finding(column="b"))


def test_fingerprint_distinguishes_connection_and_table():
    base = _schema_finding()
    other_conn = _schema_finding()
    other_conn.connection_name = "replica"
    other_table = _schema_finding()
    other_table.table_name = "customers"
    assert len({fingerprint(base), fingerprint(other_conn), fingerprint(other_table)}) == 3


def test_fingerprint_unknown_check_type_uses_table_only():
    a = make_finding("custom", details={"anything": 1})
    b = make_finding("custom", details={"anything": 2})
    assert fingerprint(a) == fingerprint(b)


# --- apply_lifecycle ---


def test_apply_lifecycle_statuses():
    new, ongoing, escalated, deescalated = (
        _schema_finding(column="new"),
        _schema_finding(column="same"),
        _schema_finding("error", column="worse"),
        _schema_finding("warning", column="better"),
    )
    previous = {
        fingerprint(ongoing): PriorFinding(id=1, severity="error"),
        fingerprint(escalated): PriorFinding(id=2, severity="warning"),
        fingerprint(deescalated): PriorFinding(id=3, severity="error"),
    }
    apply_lifecycle([new, ongoing, escalated, deescalated], previous)

    assert new.status == FindingStatus.NEW.value
    assert ongoing.status == FindingStatus.ONGOING.value
    assert escalated.status == FindingStatus.ESCALATED.value
    assert deescalated.status == FindingStatus.ONGOING.value
    assert all(f.fingerprint for f in (new, ongoing, escalated, deescalated))
    assert needs_attention(new) and needs_attention(escalated)
    assert not needs_attention(ongoing)


# --- record_check_run (SQLite) ---


def test_first_run_is_new_and_repeat_is_ongoing(state_db):
    first = [_schema_finding()]
    state_db.record_check_run(first, SCOPE)
    assert first[0].status == "new"
    assert first[0].id is not None

    second = [_schema_finding()]
    state_db.record_check_run(second, SCOPE)
    assert second[0].status == "ongoing"
    assert second[0].id != first[0].id


def test_resolved_then_reappearing_is_new(state_db):
    state_db.record_check_run([_schema_finding()], SCOPE)
    state_db.record_check_run([], SCOPE)  # clean run resolves it

    again = [_schema_finding()]
    state_db.record_check_run(again, SCOPE)
    assert again[0].status == "new"


def test_partial_run_does_not_resolve_other_scopes(state_db):
    state_db.record_check_run([_schema_finding()], SCOPE)
    # A --select volume run says nothing about schema findings
    state_db.record_check_run([], {("primary", "volume")})

    again = [_schema_finding()]
    state_db.record_check_run(again, SCOPE)
    assert again[0].status == "ongoing"


def test_escalation_detected(state_db):
    state_db.record_check_run([_schema_finding("warning")], SCOPE)
    worse = [_schema_finding("error")]
    state_db.record_check_run(worse, SCOPE)
    assert worse[0].status == "escalated"


def test_disposition_carries_over_to_ongoing(state_db):
    first = [_schema_finding()]
    state_db.record_check_run(first, SCOPE)
    state_db.set_disposition(first[0].id, "no_action", comment="expected")

    second = [_schema_finding()]
    state_db.record_check_run(second, SCOPE)

    assert second[0].disposition == "no_action"
    assert state_db.get_current_dispositions([second[0].id]) == {second[0].id: "no_action"}
    history = state_db.get_disposition_history(second[0].id)
    assert history[0]["created_by"] == "olly"
    assert f"#{first[0].id}" in history[0]["comment"]


def test_disposition_not_carried_to_escalated(state_db):
    first = [_schema_finding("warning")]
    state_db.record_check_run(first, SCOPE)
    state_db.set_disposition(first[0].id, "no_action")

    worse = [_schema_finding("error")]
    state_db.record_check_run(worse, SCOPE)
    assert worse[0].disposition == "not_started"
    assert state_db.get_current_dispositions([worse[0].id]) == {}


def test_not_started_disposition_is_not_copied(state_db):
    first = [_schema_finding()]
    state_db.record_check_run(first, SCOPE)
    state_db.set_disposition(first[0].id, "not_started")

    second = [_schema_finding()]
    state_db.record_check_run(second, SCOPE)
    assert state_db.get_current_dispositions([second[0].id]) == {}


def test_legacy_findings_without_fingerprint_are_ignored(state_db):
    state_db.store_findings([_schema_finding()])  # pre-lifecycle row, no run recorded
    current = [_schema_finding()]
    state_db.record_check_run(current, SCOPE)
    assert current[0].status == "new"


def test_sqlite_migration_adds_fingerprint_column(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE findings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at TEXT NOT NULL, connection_name TEXT NOT NULL, "
        "check_type TEXT NOT NULL, severity TEXT NOT NULL, schema_name TEXT NOT NULL, "
        "table_name TEXT NOT NULL, description TEXT NOT NULL, details TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    with StateDB(db_path=db_path) as db:
        cols = {r[1] for r in db.conn.execute("PRAGMA table_info(findings)")}
        assert "fingerprint" in cols
        findings = [_schema_finding()]
        db.record_check_run(findings, SCOPE)
        assert findings[0].status == "new"


# --- record_check_run (warehouse) ---


@pytest.fixture
def wss():
    conn = ibis.duckdb.connect(":memory:")
    return WarehouseStateStore(conn, "_olly_test", "duckdb", create_tables=True)


def test_warehouse_lifecycle_and_carry_over(wss):
    first = [_schema_finding()]
    wss.record_check_run(first, SCOPE)
    assert first[0].status == "new"
    assert first[0].id is not None
    wss.set_disposition(first[0].id, "in_progress")

    second = [_schema_finding()]
    wss.record_check_run(second, SCOPE)
    assert second[0].status == "ongoing"
    assert second[0].disposition == "in_progress"


def test_warehouse_create_tables_upgrades_old_findings_table():
    conn = ibis.duckdb.connect(":memory:")
    conn.raw_sql('CREATE SCHEMA "_olly_old"')
    conn.raw_sql(
        'CREATE TABLE "_olly_old"."findings" (id BIGINT, created_at VARCHAR, '
        "connection_name VARCHAR, check_type VARCHAR, severity VARCHAR, "
        "schema_name VARCHAR, table_name VARCHAR, description VARCHAR, details VARCHAR)"
    )
    store = WarehouseStateStore(conn, "_olly_old", "duckdb", create_tables=True)
    findings = [_schema_finding()]
    store.record_check_run(findings, SCOPE)
    assert findings[0].status == "new"


# --- run_checks integration ---


def test_run_checks_marks_repeat_findings_ongoing(olly_config, duckdb_path):
    take_snapshot(olly_config)
    conn = duckdb.connect(str(duckdb_path))
    conn.execute("ALTER TABLE customers DROP COLUMN email")
    conn.close()
    take_snapshot(olly_config)

    first, _, _ = run_checks(olly_config, select_checks={"schema"})
    assert [f.status for f in first] == ["new"]

    # Unrelated partial run in between must not resolve the schema finding
    run_checks(olly_config, select_checks={"volume"})

    second, _, _ = run_checks(olly_config, select_checks={"schema"})
    assert [f.status for f in second] == ["ongoing"]
    assert second[0].fingerprint == first[0].fingerprint


# --- Slack ---


def _mock_response():
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_slack_only_new_skips_ongoing():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test")
    ongoing = _schema_finding()
    ongoing.status = "ongoing"
    with patch("urllib.request.urlopen") as mock_open:
        send_slack_alert(config, [ongoing], [])
        mock_open.assert_not_called()


def test_slack_only_new_keeps_new_and_escalated():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test")
    new = _schema_finding(column="a")
    escalated = _schema_finding(column="b")
    escalated.status = "escalated"
    ongoing = _schema_finding(column="c")
    ongoing.status = "ongoing"
    with patch("urllib.request.urlopen", return_value=_mock_response()) as mock_open:
        send_slack_alert(config, [new, escalated, ongoing], [])
        body = json.loads(mock_open.call_args[0][0].data)
    assert "2 error(s)" in body["blocks"][0]["text"]["text"]


def test_slack_only_new_disabled_sends_ongoing():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", only_new=False)
    ongoing = _schema_finding()
    ongoing.status = "ongoing"
    with patch("urllib.request.urlopen", return_value=_mock_response()) as mock_open:
        send_slack_alert(config, [ongoing], [])
        mock_open.assert_called_once()


# --- fail_on ---


def _dbt_issue(severity="error"):
    return DbtFinding(
        resource_type="test", severity=severity, unique_id="test.p.t",
        status="fail", execution_time=0.1, description="failed",
    )


@pytest.mark.parametrize(
    ("fail_on", "severity", "status", "expected"),
    [
        ("warning", "warning", "ongoing", True),
        ("error", "warning", "new", False),
        ("error", "error", "ongoing", True),
        ("new", "error", "ongoing", False),
        ("new", "warning", "new", True),
        ("new", "error", "escalated", True),
        ("none", "error", "new", False),
    ],
)
def test_should_fail(fail_on, severity, status, expected):
    finding = make_finding("schema", severity)
    finding.status = status
    assert should_fail([finding], [], fail_on) is expected


def test_should_fail_counts_dbt_issues():
    assert should_fail([], [_dbt_issue("error")], "error")
    assert not should_fail([], [_dbt_issue("warning")], "error")
    assert should_fail([], [_dbt_issue("warning")], "new")
    assert not should_fail([], [], "warning")


def test_validate_config_rejects_unknown_fail_on():
    config = make_config()
    config.settings.fail_on = "sometimes"
    assert any("fail_on" in w for w in validate_config(config))
