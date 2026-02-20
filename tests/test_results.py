"""Tests for results.py output serialization."""

import json

from olly.models import CostRecord, DbtFinding, Finding
from olly.results import write_findings_json


def test_write_findings_with_cost_records(tmp_path):
    """write_findings_json includes cost_summary when cost_records provided."""
    findings = [
        Finding(
            check_type="schema",
            severity="warning",
            schema_name="main",
            table_name="orders",
            description="Column added",
        ),
    ]
    cost_records = [
        CostRecord(
            schema_name="main",
            table_name="orders",
            user_email="u@x.com",
            total_bytes_billed=1_000_000,
            estimated_cost_usd=10.0,
            query_count=5,
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json(findings, path=path, cost_records=cost_records)

    data = json.loads(path.read_text())
    assert "cost_summary" in data
    assert data["cost_summary"]["total_cost_usd"] == 10.0


def test_write_findings_with_dbt_findings(tmp_path):
    """write_findings_json includes dbt_findings when provided."""
    dbt_findings = [
        DbtFinding(
            resource_type="model",
            unique_id="model.my_project.orders",
            status="fail",
            severity="error",
            execution_time=1.5,
            description="Model failed",
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json([], path=path, dbt_findings=dbt_findings)

    data = json.loads(path.read_text())
    assert "dbt_findings" in data
    assert len(data["dbt_findings"]) == 1


def test_finding_connection_name_default_in_json(tmp_path):
    """Finding with default connection_name serializes as empty string."""
    findings = [
        Finding(
            check_type="schema",
            severity="warning",
            schema_name="main",
            table_name="orders",
            description="Column added",
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json(findings, path=path)

    data = json.loads(path.read_text())
    assert len(data["findings"]) == 1
    finding = data["findings"][0]
    assert "connection_name" in finding
    assert finding["connection_name"] == ""


def test_finding_connection_name_in_json(tmp_path):
    """Finding with explicit connection_name includes it in JSON output."""
    findings = [
        Finding(
            check_type="schema",
            severity="warning",
            schema_name="main",
            table_name="orders",
            description="Column added",
            connection_name="warehouse_a",
        ),
        Finding(
            check_type="volume",
            severity="error",
            schema_name="analytics",
            table_name="events",
            description="Row count anomaly",
            connection_name="warehouse_b",
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json(findings, path=path)

    data = json.loads(path.read_text())
    assert len(data["findings"]) == 2
    assert data["findings"][0]["connection_name"] == "warehouse_a"
    assert data["findings"][1]["connection_name"] == "warehouse_b"


def test_mixed_connection_names_in_json(tmp_path):
    """Findings from different connections coexist correctly in JSON output."""
    findings = [
        Finding(
            check_type="schema",
            severity="warning",
            schema_name="main",
            table_name="orders",
            description="Column added",
            connection_name="prod",
        ),
        Finding(
            check_type="freshness",
            severity="error",
            schema_name="main",
            table_name="customers",
            description="Table is stale",
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json(findings, path=path)

    data = json.loads(path.read_text())
    assert len(data["findings"]) == 2
    # First finding has explicit connection_name
    assert data["findings"][0]["connection_name"] == "prod"
    # Second finding uses default empty string
    assert data["findings"][1]["connection_name"] == ""


def test_write_findings_json_structure(tmp_path):
    """write_findings_json produces the expected top-level JSON structure."""
    findings = [
        Finding(
            check_type="volume",
            severity="error",
            schema_name="analytics",
            table_name="events",
            description="Row count anomaly",
            details={"z_score": 3.5},
            connection_name="dwh",
        ),
    ]
    path = tmp_path / "findings.json"
    write_findings_json(findings, path=path)

    data = json.loads(path.read_text())
    assert "generated_at" in data
    assert "findings" in data
    # dbt_findings and cost_summary absent when not provided
    assert "dbt_findings" not in data
    assert "cost_summary" not in data

    finding = data["findings"][0]
    assert finding == {
        "check_type": "volume",
        "severity": "error",
        "schema_name": "analytics",
        "table_name": "events",
        "description": "Row count anomaly",
        "details": {"z_score": 3.5},
        "connection_name": "dwh",
    }


def test_write_findings_empty_list(tmp_path):
    """write_findings_json works with no findings, dbt_findings, or cost_records."""
    path = tmp_path / "findings.json"
    write_findings_json([], path=path)

    data = json.loads(path.read_text())
    assert data["findings"] == []
    assert "dbt_findings" not in data
    assert "cost_summary" not in data
