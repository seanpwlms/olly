from __future__ import annotations

from olly.config import ContractsConfig, IntegrityConfig, OllyConfig
from olly.dashboard.data_checks import get_contracts_page_data, get_integrity_page_data
from olly.models import Finding, IntegrityMethod, Sync


# ── data_checks.py unit tests ──


def test_get_contracts_page_data_not_configured():
    config = OllyConfig(contracts=ContractsConfig(module=None))
    result = get_contracts_page_data([], config)
    assert result.configured is False
    assert result.total_count == 0


def test_get_contracts_page_data_pass_fail(monkeypatch):
    from olly.contracts import ColumnContract, TableSpec

    specs = [
        TableSpec("main", "orders", False, {"id": ColumnContract(int, False)}),
        TableSpec("main", "customers", False, {"name": ColumnContract(str, True)}),
    ]

    monkeypatch.setattr(
        "olly.contracts.load_contracts", lambda module, config_path: specs,
    )

    findings = [
        Finding("contracts", "error", "main", "orders", "Missing column: id"),
    ]
    config = OllyConfig(contracts=ContractsConfig(module="fake_module.py"))
    result = get_contracts_page_data(findings, config)

    assert result.configured is True
    assert result.total_count == 2
    assert result.fail_count == 1
    assert result.pass_count == 1
    assert result.contracts[0].status == "fail"
    assert len(result.contracts[0].findings) == 1
    assert result.contracts[1].status == "pass"
    assert len(result.contracts[1].columns) == 1


def test_get_integrity_page_data_not_configured():
    config = OllyConfig(integrity=IntegrityConfig(module=None))
    result = get_integrity_page_data([], config)
    assert result.configured is False
    assert result.total_count == 0


def test_get_integrity_page_data_pass_fail(monkeypatch):
    syncs = [
        Sync(
            name="orders_count",
            source="raw",
            target="warehouse",
            source_table="main.orders",
            target_table="public.orders",
            method=IntegrityMethod.COUNT,
        ),
        Sync(
            name="customers_count",
            source="raw",
            target="warehouse",
            source_table="main.customers",
            target_table="public.customers",
            method=IntegrityMethod.COUNT,
        ),
    ]

    monkeypatch.setattr(
        "olly.checks.integrity.load_syncs", lambda module, config_path: syncs,
    )

    findings = [
        Finding(
            "integrity", "error", "main", "orders", "Count mismatch",
            details={"pipeline": "orders_count"},
        ),
    ]
    config = OllyConfig(integrity=IntegrityConfig(module="fake_module.py"))
    result = get_integrity_page_data(findings, config)

    assert result.configured is True
    assert result.total_count == 2
    assert result.fail_count == 1
    assert result.pass_count == 1
    assert result.syncs[0].status == "fail"
    assert result.syncs[0].method == "count"
    assert len(result.syncs[0].findings) == 1
    assert result.syncs[1].status == "pass"


# ── contracts/integrity API route tests ──


def test_api_contracts_not_configured(dashboard_client, monkeypatch):
    monkeypatch.setattr(
        "olly.dashboard.api_routes.load_config",
        lambda: OllyConfig(contracts=ContractsConfig(module=None)),
    )
    resp = dashboard_client.get("/api/contracts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["total_count"] == 0


def test_api_contracts_with_data(dashboard_client, monkeypatch):
    from olly.contracts import ColumnContract, TableSpec

    specs = [
        TableSpec("main", "orders", False, {"id": ColumnContract(int, False)}),
    ]

    monkeypatch.setattr(
        "olly.contracts.load_contracts", lambda module, config_path: specs,
    )
    monkeypatch.setattr(
        "olly.dashboard.api_routes.load_config",
        lambda: OllyConfig(contracts=ContractsConfig(module="contracts.py")),
    )

    resp = dashboard_client.get("/api/contracts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["total_count"] == 1
    assert data["contracts"][0]["table_name"] == "orders"
    assert "last_check_time" in data


def test_api_integrity_not_configured(dashboard_client, monkeypatch):
    monkeypatch.setattr(
        "olly.dashboard.api_routes.load_config",
        lambda: OllyConfig(integrity=IntegrityConfig(module=None)),
    )
    resp = dashboard_client.get("/api/integrity")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["total_count"] == 0


def test_api_integrity_with_data(dashboard_client, monkeypatch):
    syncs = [
        Sync(
            name="orders_count",
            source="raw",
            target="warehouse",
            source_table="main.orders",
            target_table="public.orders",
            method=IntegrityMethod.COUNT,
        ),
    ]

    monkeypatch.setattr(
        "olly.checks.integrity.load_syncs", lambda module, config_path: syncs,
    )
    monkeypatch.setattr(
        "olly.dashboard.api_routes.load_config",
        lambda: OllyConfig(integrity=IntegrityConfig(module="integrity.py")),
    )

    resp = dashboard_client.get("/api/integrity")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["total_count"] == 1
    assert data["syncs"][0]["name"] == "orders_count"
    assert data["syncs"][0]["method"] == "count"
    assert "last_check_time" in data
