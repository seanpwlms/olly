from __future__ import annotations

import json
from pathlib import Path

from olly.checks.dbt import check_dbt
from olly.config import DbtConfig


def _write_run_results(
    path: Path, results: list[dict], invocation_id: str = "abc-123"
) -> None:
    """Write a minimal run_results.json fixture."""
    data = {
        "metadata": {"invocation_id": invocation_id},
        "results": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_model_error(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "model.project.stg_payments",
                "status": "error",
                "execution_time": 3.2,
                "message": "Compilation error",
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].resource_type == "model"
    assert findings[0].unique_id == "model.project.stg_payments"
    assert findings[0].description == "Compilation error"


def test_test_failure(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "test.project.not_null_orders_id",
                "status": "fail",
                "execution_time": 0.4,
                "message": "Test failed",
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].resource_type == "test"
    assert findings[0].status == "fail"


def test_test_warning(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "test.project.accepted_values_status",
                "status": "warn",
                "execution_time": 0.3,
                "message": "Got 2 results, configured to warn if != 0",
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].resource_type == "test"


def test_all_passing(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "model.project.orders",
                "status": "success",
                "execution_time": 1.2,
            },
            {
                "unique_id": "test.project.not_null_id",
                "status": "pass",
                "execution_time": 0.1,
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 2
    assert all(f.severity == "pass" for f in findings)


def test_missing_file(tmp_path: Path) -> None:
    rr = tmp_path / "nonexistent" / "run_results.json"
    findings = check_dbt(rr, DbtConfig())
    assert findings == []


def test_include_skipped_true(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "model.project.orders",
                "status": "skipped",
                "execution_time": 0.0,
            },
        ],
    )
    settings = DbtConfig(include_skipped=True)
    findings = check_dbt(rr, settings)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].status == "skipped"


def test_include_skipped_false(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "model.project.orders",
                "status": "skipped",
                "execution_time": 0.0,
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig(include_skipped=False))
    # Skipped nodes are excluded (not even as pass) when include_skipped is false
    assert findings == []


def test_snapshot_error(tmp_path: Path) -> None:
    """Snapshot nodes with error status are treated like model errors."""
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "snapshot.project.snap_orders",
                "status": "error",
                "execution_time": 1.0,
                "message": "Database error",
            },
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].resource_type == "snapshot"


def test_details_include_invocation_id(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {
                "unique_id": "model.project.orders",
                "status": "error",
                "execution_time": 1.0,
                "message": "fail",
            },
        ],
        invocation_id="run-42",
    )
    findings = check_dbt(rr, DbtConfig())
    assert findings[0].details["invocation_id"] == "run-42"


def test_mixed_results(tmp_path: Path) -> None:
    """Multiple result types in one file."""
    rr = tmp_path / "run_results.json"
    _write_run_results(
        rr,
        [
            {"unique_id": "model.p.a", "status": "success", "execution_time": 1.0},
            {
                "unique_id": "model.p.b",
                "status": "error",
                "execution_time": 2.0,
                "message": "err",
            },
            {
                "unique_id": "test.p.c",
                "status": "fail",
                "execution_time": 0.5,
                "message": "fail",
            },
            {
                "unique_id": "test.p.d",
                "status": "warn",
                "execution_time": 0.3,
                "message": "warn",
            },
            {"unique_id": "model.p.e", "status": "success", "execution_time": 120.0},
        ],
    )
    findings = check_dbt(rr, DbtConfig())
    assert len(findings) == 5
    severities = [f.severity for f in findings]
    assert severities.count("error") == 2
    assert severities.count("warning") == 1
    assert severities.count("pass") == 2
