from __future__ import annotations

from olly.models import CostRecord, Finding
from olly.state import StateDB
from helpers import patch_dashboard


def test_api_overview(dashboard_client):
    resp = dashboard_client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["error_count"] == 1
    assert data["stats"]["warning_count"] == 1
    assert "top_tables" in data
    assert "findings_trend" in data
    assert isinstance(data["findings_by_connection"], dict)


def test_api_findings_no_filter(dashboard_client):
    resp = dashboard_client.get("/api/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert "orders" in str(data["findings"])


def test_api_findings_filter_check_type(dashboard_client):
    resp = dashboard_client.get("/api/findings?check_type=schema")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["check_type"] == "schema" for f in data["findings"])


def test_api_findings_filter_severity(dashboard_client):
    resp = dashboard_client.get("/api/findings?severity=warning")
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["severity"] == "warning" for f in data["findings"])


def test_api_table_detail(dashboard_client):
    resp = dashboard_client.get("/api/table/main/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["table_info"]["table_name"] == "orders"
    assert data["volume_stats"]["current"] == 100


def test_api_tables(dashboard_client):
    resp = dashboard_client.get("/api/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])
    assert data["total"] >= 1


def test_api_tables_search(dashboard_client):
    resp = dashboard_client.get("/api/tables?search=orders")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])


def test_api_tables_search_no_match(dashboard_client):
    resp = dashboard_client.get("/api/tables?search=zzzzz")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tables"]) == 0


def test_api_tables_sort(dashboard_client):
    resp = dashboard_client.get("/api/tables?sort=row_count&order=desc")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["table"] == "orders" for t in data["tables"])


def test_api_table_detail_not_found_graceful(dashboard_client):
    resp = dashboard_client.get("/api/table/main/nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["table_info"] is None


def test_api_history(dashboard_client):
    resp = dashboard_client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == 30


def test_api_connections(dashboard_client):
    resp = dashboard_client.get("/api/connections")
    assert resp.status_code == 200
    data = resp.json()
    assert "test_connection" in data["connections"]


def test_api_dbt(dashboard_client):
    resp = dashboard_client.get("/api/dbt")
    assert resp.status_code == 200
    data = resp.json()
    assert "dbt_stats" in data
    assert "dbt_findings" in data
    assert "execution_leaderboard" in data
    assert "run_history" in data
    assert "total_execution_time" in data["dbt_stats"]
    assert "total_failures" in data["dbt_stats"]


def test_api_dbt_previous_sql(tmp_path, monkeypatch):
    """GET /dbt/node/{unique_id}/previous-sql returns previous compiled code."""
    from olly.models import DbtFinding, DbtRunRecord

    state_db_path = tmp_path / ".olly" / "state.db"
    state_db_path.parent.mkdir(parents=True)
    state_db = StateDB(db_path=state_db_path)
    state_db.init_db()

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
    state_db.close()

    client = patch_dashboard(monkeypatch, state_db_path, tmp_path)
    resp = client.get(f"/api/dbt/node/model.p.orders/previous-sql?dbt_run_id={run2}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["previous_sql"] == "SELECT 1"


def test_api_dbt_previous_sql_no_history(tmp_path, monkeypatch):
    """Returns null when no previous run exists."""
    from olly.models import DbtFinding, DbtRunRecord

    state_db_path = tmp_path / ".olly" / "state.db"
    state_db_path.parent.mkdir(parents=True)
    state_db = StateDB(db_path=state_db_path)
    state_db.init_db()

    run1 = state_db.store_dbt_run(DbtRunRecord("inv-1", 10.0, 1, 0, 0, 1))
    state_db.store_dbt_findings([
        DbtFinding("model", "pass", "model.p.orders", "success", 5.0, "ok",
                   details={"compiled_code": "SELECT 1"}),
    ], dbt_run_id=run1)
    state_db.close()

    client = patch_dashboard(monkeypatch, state_db_path, tmp_path)
    resp = client.get(f"/api/dbt/node/model.p.orders/previous-sql?dbt_run_id={run1}")
    assert resp.status_code == 200
    assert resp.json()["previous_sql"] is None


def test_api_usage_empty(dashboard_client):
    resp = dashboard_client.get("/api/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert data["stats"]["unused_count"] == 0


def test_api_usage_with_findings(tmp_path, monkeypatch):
    """Usage API with usage findings and cost data."""
    state_db_path = tmp_path / ".olly" / "state.db"
    state_db_path.parent.mkdir(parents=True)
    state_db = StateDB(db_path=state_db_path)
    state_db.init_db()

    usage_findings = [
        Finding(
            "usage", "error", "main", "old_table", "Unused table",
            details={"last_queried_at": None, "lookback_days": 90},
        ),
        Finding(
            "usage", "warning", "main", "stale_table", "Stale table",
            details={"last_queried_at": "2025-06-01T00:00:00", "days_unused": 45.0},
        ),
    ]
    state_db.store_findings(usage_findings)
    cost_records = [
        CostRecord("main", "orders", "alice@co.com", 5000000, 25.00, 10),
        CostRecord("main", "users", "bob@co.com", 2000000, 8.50, 3),
    ]
    state_db.store_cost_data(cost_records)
    state_db.close()

    client = patch_dashboard(monkeypatch, state_db_path, tmp_path)
    resp = client.get("/api/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["unused_count"] == 1
    assert data["stats"]["stale_count"] == 1
    assert data["cost_summary"]["total_cost_usd"] == 33.50
    assert any("alice@co.com" in u["user"] for u in data["cost_summary"]["top_users"])


# --- Disposition API route tests ---


def test_api_set_disposition(dashboard_client):
    """PUT /findings/{id}/disposition sets disposition."""
    resp = dashboard_client.put(
        "/api/findings/1/disposition",
        json={"disposition": "in_progress", "comment": "Looks fine"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "disposition_id" in data


def test_api_set_disposition_invalid(dashboard_client):
    """Invalid disposition value returns 400."""
    resp = dashboard_client.put(
        "/api/findings/1/disposition",
        json={"disposition": "bogus_value"},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_api_bulk_disposition(dashboard_client):
    """PUT /findings/bulk-disposition sets disposition on multiple findings."""
    resp = dashboard_client.put(
        "/api/findings/bulk-disposition",
        json={"finding_ids": [1, 2], "disposition": "in_progress"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 2


def test_api_bulk_disposition_empty(dashboard_client):
    """Bulk disposition with empty list succeeds with count 0."""
    resp = dashboard_client.put(
        "/api/findings/bulk-disposition",
        json={"finding_ids": [], "disposition": "in_progress"},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_api_bulk_disposition_invalid(dashboard_client):
    """Invalid disposition in bulk request returns 400."""
    resp = dashboard_client.put(
        "/api/findings/bulk-disposition",
        json={"finding_ids": [1], "disposition": "not_real"},
    )
    assert resp.status_code == 400


def test_api_disposition_history(dashboard_client):
    """GET /findings/{id}/dispositions returns history."""
    # First set a disposition so there's history
    dashboard_client.put(
        "/api/findings/1/disposition",
        json={"disposition": "in_progress", "comment": "initial"},
    )
    resp = dashboard_client.get("/api/findings/1/dispositions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["finding_id"] == 1
    assert "current_disposition" in data
    assert "history" in data
