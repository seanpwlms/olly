from __future__ import annotations

import logging

from olly.config import OllyConfig
from olly.dashboard.schemas import (
    ContractColumnStatusModel,
    ContractsPageData,
    ContractStatusModel,
    FindingModel,
    IntegrityPageData,
    SyncStatusModel,
)
from olly.models import Finding

logger = logging.getLogger(__name__)


# ── Contracts page ──


def get_contracts_page_data(
    findings: list[Finding], config: OllyConfig,
) -> ContractsPageData:
    """Build contracts page data by cross-referencing specs with findings."""
    if not config.contracts.module:
        return ContractsPageData(configured=False)

    from olly.contracts import load_contracts

    try:
        specs = load_contracts(config.contracts.module, config.config_path)
    except (ImportError, AttributeError, ValueError) as exc:
        logger.warning("Failed to load contracts module: %s", exc)
        return ContractsPageData(configured=False)

    contract_findings = [f for f in findings if f.check_type == "contracts"]

    statuses: list[ContractStatusModel] = []
    for spec in specs:
        matched = [
            f for f in contract_findings
            if f.schema_name == spec.schema_name and f.table_name == spec.table_name
        ]
        columns = [
            ContractColumnStatusModel(
                column_name=name,
                expected_type=col.dtype.__name__,
                nullable=col.nullable,
            )
            for name, col in spec.columns.items()
        ]
        statuses.append(ContractStatusModel(
            schema_name=spec.schema_name,
            table_name=spec.table_name,
            strict=spec.strict,
            connection_name=spec.connection_name,
            columns=columns,
            status="fail" if matched else "pass",
            findings=[FindingModel.model_validate(f) for f in matched],
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


def get_integrity_page_data(
    findings: list[Finding], config: OllyConfig,
) -> IntegrityPageData:
    """Build integrity page data by cross-referencing syncs with findings."""
    if not config.integrity.module:
        return IntegrityPageData(configured=False)

    from olly.checks.integrity import load_syncs

    try:
        syncs = load_syncs(config.integrity.module, config.config_path)
    except (ImportError, AttributeError, ValueError) as exc:
        logger.warning("Failed to load integrity module: %s", exc)
        return IntegrityPageData(configured=False)

    integrity_findings = [f for f in findings if f.check_type == "integrity"]

    statuses: list[SyncStatusModel] = []
    for sync in syncs:
        matched = [
            f for f in integrity_findings
            if f.details.get("pipeline") == sync.name
        ]
        statuses.append(SyncStatusModel(
            name=sync.name,
            source=sync.source,
            target=sync.target,
            source_table=sync.source_table,
            target_table=sync.target_table,
            method=sync.method.value,
            key=sync.key,
            severity=sync.severity,
            status="fail" if matched else "pass",
            findings=[FindingModel.model_validate(f) for f in matched],
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
