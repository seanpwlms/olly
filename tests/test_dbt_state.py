"""Tests for dbt run/node timing state store methods."""

from __future__ import annotations

from olly.models import DbtFinding, DbtRunRecord


def test_store_and_retrieve_dbt_run(state_db):
    """Store a dbt run, retrieve it from history."""
    run = DbtRunRecord("inv-1", 42.5, 10, 2, 1, 7)
    run_id = state_db.store_dbt_run(run)
    assert run_id is not None

    history = state_db.get_dbt_run_history(limit=10)
    assert len(history) == 1
    assert history[0].invocation_id == "inv-1"
    assert history[0].elapsed_time == 42.5
    assert history[0].total_nodes == 10
    assert history[0].error_count == 2


def test_dbt_run_history_ordering(state_db):
    """History returns newest first."""
    state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 5, 0, 0, 5))
    state_db.store_dbt_run(DbtRunRecord("inv-2", 20.0, 5, 1, 0, 4))
    state_db.store_dbt_run(DbtRunRecord("inv-3", 30.0, 5, 2, 0, 3))

    history = state_db.get_dbt_run_history(limit=10)
    assert len(history) == 3
    assert history[0].invocation_id == "inv-3"  # newest
    assert history[2].invocation_id == "inv-1"  # oldest


def test_store_and_retrieve_node_timings(state_db):
    """Store node timings and retrieve per-node history."""
    findings = [
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok"),
        DbtFinding("test", "pass", "test.p.not_null", "pass", 0.5, "ok"),
    ]

    run_id = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 2, 0, 0, 2))
    state_db.store_dbt_node_timings(run_id, findings)

    history = state_db.get_dbt_node_execution_history("model.p.orders", depth=10)
    assert len(history) == 1
    assert history[0] == 5.0


def test_node_timing_timeseries(state_db):
    """Node timing timeseries returns (created_at, execution_time) pairs."""
    f = DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok")

    run_id = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_node_timings(run_id, [f])

    f2 = DbtFinding("model", "pass", "model.p.orders", "success", 8.0, "ok")
    run_id2 = state_db.store_dbt_run(DbtRunRecord("inv-2", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_node_timings(run_id2, [f2])

    ts = state_db.get_dbt_node_timing_timeseries("model.p.orders", limit=10)
    assert len(ts) == 2
    # oldest first
    assert ts[0][1] == 5.0
    assert ts[1][1] == 8.0


def test_store_dbt_findings_with_run_id(state_db):
    """Findings stored with dbt_run_id are retrieved with that run_id."""
    run_id = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 2, 0, 0, 2))
    findings = [
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT * FROM orders"}),
        DbtFinding("test", "error", "test.p.not_null", "fail", 0.5, "failed"),
    ]
    state_db.store_dbt_findings(findings, dbt_run_id=run_id)

    loaded = state_db.get_latest_dbt_findings()
    assert len(loaded) == 2
    assert all(f.dbt_run_id == run_id for f in loaded)


def test_store_dbt_findings_without_run_id(state_db):
    """Findings stored without dbt_run_id have None."""
    findings = [
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok"),
    ]
    state_db.store_dbt_findings(findings)

    loaded = state_db.get_latest_dbt_findings()
    assert len(loaded) == 1
    assert loaded[0].dbt_run_id is None


def test_get_previous_compiled_code_with_run_id(state_db):
    """Get previous compiled code using run_id linkage."""
    run1 = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT 1"}),
    ], dbt_run_id=run1)

    run2 = state_db.store_dbt_run(DbtRunRecord("inv-2", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT 2"}),
    ], dbt_run_id=run2)

    prev = state_db.get_previous_compiled_code("model.p.orders", run2)
    assert prev == "SELECT 1"


def test_get_previous_compiled_code_no_history(state_db):
    """Returns None when there's only one run."""
    run1 = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT 1"}),
    ], dbt_run_id=run1)

    prev = state_db.get_previous_compiled_code("model.p.orders", run1)
    assert prev is None


def test_get_previous_compiled_code_fallback_no_run_id(state_db):
    """Falls back to created_at ordering when run_id is None."""
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT old"}),
    ])
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT new"}),
    ])

    prev = state_db.get_previous_compiled_code("model.p.orders")
    assert prev == "SELECT old"


def test_dbt_run_history_with_timestamps(state_db):
    """History with timestamps returns (created_at, DbtRunRecord) tuples."""
    state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 5, 0, 0, 5))

    history = state_db.get_dbt_run_history_with_timestamps(limit=10)
    assert len(history) == 1
    ts, run = history[0]
    assert isinstance(ts, str)
    assert run.invocation_id == "inv-1"
