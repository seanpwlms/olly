"""Tests for dbt performance anomaly detection."""

from __future__ import annotations

from olly.checks.dbt_perf import check_dbt_performance
from olly.models import DbtFinding, DbtRunRecord


def _make_finding(unique_id: str = "model.p.orders", execution_time: float = 10.0):
    return DbtFinding(
        resource_type="model",
        severity="pass",
        unique_id=unique_id,
        status="success",
        execution_time=execution_time,
        description="model passed",
    )


def test_no_anomaly_insufficient_history(state_db):
    """No anomaly detected when history is too short."""
    f = _make_finding()
    # Store only 2 runs (less than min_history=5)
    for _ in range(2):
        run_id = state_db.store_dbt_run(DbtRunRecord("inv", 10.0, 1, 0, 0, 1))
        state_db.store_dbt_node_timings(run_id, [f])

    result = check_dbt_performance([f], state_db, threshold=3.0, min_history=5)
    assert result == []


def test_anomaly_detected(state_db):
    """A sudden spike in execution time triggers a warning."""
    f_normal = _make_finding(execution_time=10.0)
    # Store 10 normal runs
    for _ in range(10):
        run_id = state_db.store_dbt_run(DbtRunRecord("inv", 10.0, 1, 0, 0, 1))
        state_db.store_dbt_node_timings(run_id, [f_normal])

    # Now a spike
    f_spike = _make_finding(execution_time=500.0)
    run_id = state_db.store_dbt_run(DbtRunRecord("inv", 500.0, 1, 0, 0, 1))
    state_db.store_dbt_node_timings(run_id, [f_spike])

    result = check_dbt_performance([f_spike], state_db, threshold=3.0, min_history=5)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert "performance_anomaly" in result[0].details


def test_no_anomaly_normal_variation(state_db):
    """Normal variation does not trigger an anomaly."""
    times = [10.0, 11.0, 9.5, 10.5, 10.2, 9.8, 10.1, 10.3, 9.9, 10.0]
    for t in times:
        f = _make_finding(execution_time=t)
        run_id = state_db.store_dbt_run(DbtRunRecord("inv", t, 1, 0, 0, 1))
        state_db.store_dbt_node_timings(run_id, [f])

    f_current = _make_finding(execution_time=10.5)
    run_id = state_db.store_dbt_run(DbtRunRecord("inv", 10.5, 1, 0, 0, 1))
    state_db.store_dbt_node_timings(run_id, [f_current])

    result = check_dbt_performance([f_current], state_db, threshold=3.0, min_history=5)
    assert result == []


def test_skipped_nodes_ignored(state_db):
    """Skipped nodes are not checked for anomalies."""
    f = DbtFinding(
        resource_type="model",
        severity="warning",
        unique_id="model.p.orders",
        status="skipped",
        execution_time=0.0,
        description="skipped",
    )
    result = check_dbt_performance([f], state_db, threshold=3.0, min_history=5)
    assert result == []
