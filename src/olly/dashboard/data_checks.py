from __future__ import annotations

import logging
from dataclasses import dataclass

from olly.config import OllyConfig
from olly.models import Finding

logger = logging.getLogger(__name__)


# ── Contracts page ──


@dataclass
class ContractColumnStatus:
    column_name: str
    expected_type: str
    nullable: bool


@dataclass
class ContractStatus:
    schema_name: str
    table_name: str
    strict: bool
    connection_name: str | None
    columns: list[ContractColumnStatus]
    status: str  # "pass" or "fail"
    findings: list[Finding]


@dataclass
class ContractsPageData:
    contracts: list[ContractStatus]
    pass_count: int
    fail_count: int
    total_count: int
    configured: bool


def get_contracts_page_data(
    findings: list[Finding], config: OllyConfig,
) -> ContractsPageData:
    """Build contracts page data by cross-referencing specs with findings."""
    if not config.contracts.module:
        return ContractsPageData([], 0, 0, 0, configured=False)

    from olly.contracts import load_contracts

    try:
        specs = load_contracts(config.contracts.module, config.config_path)
    except (ImportError, AttributeError, ValueError) as exc:
        logger.warning("Failed to load contracts module: %s", exc)
        return ContractsPageData([], 0, 0, 0, configured=False)

    contract_findings = [f for f in findings if f.check_type == "contracts"]

    statuses: list[ContractStatus] = []
    for spec in specs:
        matched = [
            f for f in contract_findings
            if f.schema_name == spec.schema_name and f.table_name == spec.table_name
        ]
        columns = [
            ContractColumnStatus(
                column_name=name,
                expected_type=col.dtype.__name__,
                nullable=col.nullable,
            )
            for name, col in spec.columns.items()
        ]
        statuses.append(ContractStatus(
            schema_name=spec.schema_name,
            table_name=spec.table_name,
            strict=spec.strict,
            connection_name=spec.connection_name,
            columns=columns,
            status="fail" if matched else "pass",
            findings=matched,
        ))

    pass_count = sum(1 for s in statuses if s.status == "pass")
    fail_count = sum(1 for s in statuses if s.status == "fail")
    return ContractsPageData(
        contracts=statuses,
        pass_count=pass_count,
        fail_count=fail_count,
        total_count=len(statuses),
        configured=True,
    )


# ── Integrity page ──


@dataclass
class SyncStatus:
    name: str
    source: str
    target: str
    source_table: str
    target_table: str
    method: str
    key: str | None
    severity: str
    status: str  # "pass" or "fail"
    findings: list[Finding]


@dataclass
class IntegrityPageData:
    syncs: list[SyncStatus]
    pass_count: int
    fail_count: int
    total_count: int
    configured: bool


def get_integrity_page_data(
    findings: list[Finding], config: OllyConfig,
) -> IntegrityPageData:
    """Build integrity page data by cross-referencing syncs with findings."""
    if not config.integrity.module:
        return IntegrityPageData([], 0, 0, 0, configured=False)

    from olly.checks.integrity import load_syncs

    try:
        syncs = load_syncs(config.integrity.module, config.config_path)
    except (ImportError, AttributeError, ValueError) as exc:
        logger.warning("Failed to load integrity module: %s", exc)
        return IntegrityPageData([], 0, 0, 0, configured=False)

    integrity_findings = [f for f in findings if f.check_type == "integrity"]

    statuses: list[SyncStatus] = []
    for sync in syncs:
        matched = [
            f for f in integrity_findings
            if f.details.get("pipeline") == sync.name
        ]
        statuses.append(SyncStatus(
            name=sync.name,
            source=sync.source,
            target=sync.target,
            source_table=sync.source_table,
            target_table=sync.target_table,
            method=sync.method.value,
            key=sync.key,
            severity=sync.severity,
            status="fail" if matched else "pass",
            findings=matched,
        ))

    pass_count = sum(1 for s in statuses if s.status == "pass")
    fail_count = sum(1 for s in statuses if s.status == "fail")
    return IntegrityPageData(
        syncs=statuses,
        pass_count=pass_count,
        fail_count=fail_count,
        total_count=len(statuses),
        configured=True,
    )
