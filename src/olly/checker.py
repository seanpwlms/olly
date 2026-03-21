"""Core check orchestration logic for running data quality checks."""

from __future__ import annotations

import logging
from pathlib import Path

from olly.adapter import Adapter, ProgressCallback, connect_typed
from olly.config import OllyConfig
from olly.config_ops import (
    resolve_connections,
    resolve_table_settings_with_sources,
    select_schema_names,
)
from olly.checks.dbt import check_dbt
from olly.checks.dbt_perf import check_dbt_performance
from olly.checks.freshness import check_freshness
from olly.checks.integrity import load_syncs, run_syncs
from olly.checks.schema import check_schema
from olly.checks.volume import check_volume
from olly.checks.contracts import check_contracts
from olly.checks.cost import check_cost
from olly.checks.usage import check_usage
from olly.contracts import load_contracts
from olly.models import CostRecord, DbtFinding, DbtRunRecord, Finding
from olly.state import open_state

logger = logging.getLogger(__name__)


def run_checks(
    config: OllyConfig,
    adapter: Adapter | None = None,
    connection_name: str | None = None,
    on_progress: ProgressCallback | None = None,
    select_checks: set[str] | None = None,
) -> tuple[list[Finding], list[DbtFinding], list[CostRecord]]:
    """Run all enabled checks against the warehouse and return findings.

    Executes schema, contract, volume, freshness, integrity, cost, and dbt
    checks by comparing the two most recent snapshots.

    Args:
        config: Parsed Olly configuration.
        adapter: Optional pre-built adapter (only used for single-connection).
        connection_name: Optional connection name to check.
        on_progress: Optional callback invoked before each check step with
            ``(connection_name, check_name)``.
        select_checks: Optional set of check type names to run. When ``None``,
            all checks are executed.

    Returns:
        Tuple of (warehouse findings, dbt findings, cost records).
    """
    def _selected(name: str) -> bool:
        return select_checks is None or name in select_checks

    logger.info("Starting checks")
    findings: list[Finding] = []
    cost_records: list[CostRecord] = []

    per_conn_types = {"schema", "volume", "freshness", "usage", "cost", "contracts"}
    run_per_connection = select_checks is None or bool(select_checks & per_conn_types)

    connections = resolve_connections(config, connection_name) if run_per_connection else []

    snapshot_types = {"schema", "volume", "freshness", "contracts"}
    needs_snapshots = select_checks is None or bool(select_checks & snapshot_types)

    last_backend = None
    for name, nc in connections:
        if on_progress:
            on_progress(name, "connect")
        backend = adapter if adapter is not None else connect_typed(nc.connection)
        last_backend = backend

        schemas = select_schema_names(nc.selection, backend.list_schemas())

        # Usage checks (independent of snapshots)
        if _selected("usage") and config.usage.enabled:
            logger.debug("[%s] Running usage checks", name)
            if on_progress:
                on_progress(name, "usage")
            usage_findings = check_usage(
                backend, schemas, config.usage,
                all_tables=backend.list_tables(schemas),
            )
            for f in usage_findings:
                f.connection_name = name
            findings.extend(usage_findings)

        with open_state(config, backend) as state_db:
            # Cost checks (independent of snapshots)
            if _selected("cost") and config.usage.cost_enabled:
                logger.debug("[%s] Running cost checks", name)
                if on_progress:
                    on_progress(name, "cost")
                conn_cost_records, cost_findings = check_cost(
                    backend, schemas, config.usage, state_db, connection_name=name
                )
                for f in cost_findings:
                    f.connection_name = name
                findings.extend(cost_findings)
                cost_records.extend(conn_cost_records)
                if conn_cost_records:
                    state_db.store_cost_data(conn_cost_records, connection_name=name)

            # Skip snapshot-based checks if not selected or not enough snapshots
            if not needs_snapshots:
                continue

            if not state_db.has_multiple_snapshots(connection_name=name):
                logger.debug(
                    "[%s] Skipping snapshot-based checks (fewer than 2 snapshots)", name
                )
                continue

            # Get the two most recent snapshots
            latest_tables = state_db.get_latest_schema(connection_name=name)
            baseline_tables = state_db.get_second_latest_schema(connection_name=name)
            latest_volumes = state_db.get_latest_volume(connection_name=name)

            # Schema checks
            if _selected("schema"):
                logger.debug("[%s] Running schema checks", name)
                if on_progress:
                    on_progress(name, "schema")
                schema_findings = check_schema(latest_tables, baseline_tables)
                for f in schema_findings:
                    f.connection_name = name
                findings.extend(schema_findings)

            if _selected("contracts") and config.contracts.module:
                logger.debug("[%s] Running contract checks", name)
                if on_progress:
                    on_progress(name, "contracts")
                config_path = config.config_path or Path("olly.toml")
                all_contracts = load_contracts(config.contracts.module, config_path)
                contracts = [
                    c
                    for c in all_contracts
                    if c.connection_name is None or c.connection_name == name
                ]
                contract_findings = check_contracts(contracts, backend)
                for f in contract_findings:
                    f.connection_name = name
                findings.extend(contract_findings)

            # Volume checks
            if _selected("volume"):
                logger.debug("[%s] Running volume checks", name)
                if on_progress:
                    on_progress(name, "volume")
                overrides_map = {
                    (t.schema_name, t.table_name): resolve_table_settings_with_sources(
                        config.settings, nc.overrides, t.schema_name, t.table_name
                    )
                    for t in latest_tables
                }
                thresholds = {
                    key: settings.volume_zscore_threshold
                    for key, settings in overrides_map.items()
                }
                methods = {
                    key: settings.volume_method
                    for key, settings in overrides_map.items()
                }

                volume_findings = check_volume(
                    latest_volumes, state_db, config.settings, thresholds,
                    methods=methods, connection_name=name,
                )
                for f in volume_findings:
                    f.connection_name = name
                findings.extend(volume_findings)

            # Freshness checks
            if _selected("freshness"):
                logger.debug("[%s] Running freshness checks", name)
                if on_progress:
                    on_progress(name, "freshness")
                if not _selected("volume"):
                    overrides_map = {
                        (t.schema_name, t.table_name): resolve_table_settings_with_sources(
                            config.settings, nc.overrides, t.schema_name, t.table_name
                        )
                        for t in latest_tables
                    }
                freshness_findings = check_freshness(
                    backend, latest_tables, config.settings, overrides_map, state_db,
                    connection_name=name,
                )
                for f in freshness_findings:
                    f.connection_name = name
                findings.extend(freshness_findings)

    # Integrity checks (global, not per-connection)
    if _selected("integrity") and config.integrity.module:
        logger.debug("Running integrity checks")
        if on_progress:
            on_progress("", "integrity")
        config_path = config.config_path or Path("olly.toml")
        syncs = load_syncs(config.integrity.module, config_path)
        findings.extend(run_syncs(syncs, connections=config.connections))

    # dbt checks (global)
    dbt_findings: list[DbtFinding] = []
    dbt_run: DbtRunRecord | None = None
    if _selected("dbt"):
        logger.debug("Running dbt checks")
        if on_progress:
            on_progress("", "dbt")
        dbt_findings, dbt_run = _run_dbt_checks(config)

    # Store all findings in the correct state store (warehouse or SQLite)
    if findings or dbt_findings or dbt_run:
        if on_progress:
            on_progress("", "saving")
        with open_state(config, last_backend) as state_db:
            state_db.store_findings(findings)
            if dbt_run:
                run_id = state_db.store_dbt_run(dbt_run)
                state_db.store_dbt_findings(dbt_findings, dbt_run_id=run_id)
                state_db.store_dbt_node_timings(run_id, dbt_findings)
                # Per-model performance anomaly detection
                perf_findings = check_dbt_performance(
                    dbt_findings, state_db,
                    threshold=config.dbt.performance_threshold,
                    min_history=config.dbt.min_history_for_anomaly,
                )
                dbt_findings.extend(perf_findings)
                if perf_findings:
                    state_db.store_dbt_findings(perf_findings, dbt_run_id=run_id)
            else:
                state_db.store_dbt_findings(dbt_findings)

    total = len(findings) + len(dbt_findings)
    logger.info("Checks complete: %d findings", total)
    return findings, dbt_findings, cost_records


def _run_dbt_checks(
    config: OllyConfig,
) -> tuple[list[DbtFinding], DbtRunRecord | None]:
    """Run dbt checks if configured."""
    if not config.dbt.run_results_path:
        logger.info("No dbt.run_results_path configured, skipping dbt checks")
        return [], None
    run_results_path = Path(config.dbt.run_results_path)
    if not run_results_path.is_absolute() and config.config_path is not None:
        run_results_path = config.config_path.parent / run_results_path
    return check_dbt(run_results_path, config.dbt)
