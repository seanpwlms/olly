from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from dataclasses import asdict

from rich.console import Console
from rich.table import Table

from olly.adapter import Adapter, connect_typed
from olly.config import OllyConfig, load_config
from olly.config_ops import (
    filter_table_infos,
    resolve_connections,
    resolve_table_settings_with_sources,
    select_schema_names,
    validate_config,
)
from olly.logging import setup_logging
from olly.checks.dbt import check_dbt
from olly.checks.freshness import check_freshness
from olly.checks.integrity import load_syncs, run_syncs
from olly.checks.schema import check_schema
from olly.checks.volume import check_volume
from olly.checks.contracts import check_contracts
from olly.checks.cost import check_cost, summarize_costs
from olly.checks.usage import check_usage
from olly.contracts import load_contracts
from olly.models import CostRecord, DbtFinding, Finding
from olly.results import write_findings_json
from olly.slack import send_slack_alert
from olly.state import open_state

logger = logging.getLogger(__name__)

console = Console()


def run_checks(
    config: OllyConfig,
    adapter: Adapter | None = None,
    connection_name: str | None = None,
) -> tuple[list[Finding], list[DbtFinding], list[CostRecord]]:
    """Run all enabled checks against the warehouse and return findings.

    Executes schema, contract, volume, freshness, integrity, cost, and dbt
    checks by comparing the current warehouse state to the latest snapshot.

    Args:
        config: Parsed Olly configuration.
        adapter: Optional pre-built adapter (only used for single-connection).
        connection_name: Optional connection name to check.

    Returns:
        Tuple of (warehouse findings, dbt findings, cost records).
    """
    logger.info("Starting checks")
    findings: list[Finding] = []
    cost_records: list[CostRecord] = []

    connections = resolve_connections(config, connection_name)

    for name, nc in connections:
        backend = adapter if adapter is not None else connect_typed(nc.connection)

        schemas = select_schema_names(nc.selection, backend.list_schemas())
        current_tables = backend.fetch_schema_info(schemas)
        current_tables = filter_table_infos(nc.selection, current_tables)
        current_volumes = backend.fetch_row_counts(current_tables)

        # Usage checks (independent of snapshots)
        if config.usage.enabled:
            logger.debug("[%s] Running usage checks", name)
            usage_findings = check_usage(backend, schemas, config.usage)
            for f in usage_findings:
                f.connection_name = name
            findings.extend(usage_findings)

        with open_state(config, backend, nc.connection.type) as state_db:
            # Cost checks (independent of snapshots)
            if config.cost.enabled:
                logger.debug("[%s] Running cost checks", name)
                conn_cost_records, cost_findings = check_cost(
                    backend, schemas, config.cost, state_db, connection_name=name
                )
                for f in cost_findings:
                    f.connection_name = name
                findings.extend(cost_findings)
                cost_records.extend(conn_cost_records)
                if conn_cost_records:
                    snap_id = state_db.create_snapshot(connection_name=name)
                    state_db.store_cost_data(snap_id, conn_cost_records)

            if not state_db.has_snapshots(connection_name=name):
                continue

            baseline_tables = state_db.get_latest_schema(connection_name=name)

            # Schema checks
            logger.debug("[%s] Running schema checks", name)
            schema_findings = check_schema(current_tables, baseline_tables)
            for f in schema_findings:
                f.connection_name = name
            findings.extend(schema_findings)

            logger.debug("[%s] Running contract checks", name)
            if config.contracts.module:
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
            logger.debug("[%s] Running volume checks", name)
            overrides_map = {
                (t.schema_name, t.table_name): resolve_table_settings_with_sources(
                    config.settings, nc.overrides, t.schema_name, t.table_name
                )
                for t in current_tables
            }
            thresholds = {
                key: settings.volume_zscore_threshold
                for key, settings in overrides_map.items()
            }

            volume_findings = check_volume(
                current_volumes, state_db, config.settings, thresholds,
                connection_name=name,
            )
            for f in volume_findings:
                f.connection_name = name
            findings.extend(volume_findings)

            # Freshness checks
            logger.debug("[%s] Running freshness checks", name)
            freshness_findings = check_freshness(
                backend, current_tables, config.settings, overrides_map, state_db,
                connection_name=name,
            )
            for f in freshness_findings:
                f.connection_name = name
            findings.extend(freshness_findings)

    # Integrity checks (global, not per-connection)
    logger.debug("Running integrity checks")
    if config.integrity.module:
        config_path = config.config_path or Path("olly.toml")
        syncs = load_syncs(config.integrity.module, config_path)
        findings.extend(run_syncs(syncs, sources=config.sources))

    # dbt checks (global)
    logger.debug("Running dbt checks")
    dbt_findings = _run_dbt_checks(config)

    total = len(findings) + len(dbt_findings)
    logger.info("Checks complete: %d findings", total)
    return findings, dbt_findings, cost_records


def _run_dbt_checks(config: OllyConfig) -> list[DbtFinding]:
    """Run dbt checks if configured."""
    if not config.dbt.run_results_path:
        return []
    run_results_path = Path(config.dbt.run_results_path)
    if not run_results_path.is_absolute() and config.config_path is not None:
        run_results_path = config.config_path.parent / run_results_path
    return check_dbt(run_results_path, config.dbt)


def print_findings_table(findings: list[Finding]) -> None:
    """Render findings as a Rich table to the console.

    Args:
        findings: List of findings to display. Prints nothing when empty.
    """
    if not findings:
        return

    show_connection = any(f.connection_name for f in findings)

    table = Table(title="Findings", show_lines=True)
    if show_connection:
        table.add_column("Connection", style="magenta", width=12)
    table.add_column("Check", style="cyan", width=10)
    table.add_column("Severity", width=8)
    table.add_column("Table", style="blue")
    table.add_column("Description")

    for f in findings:
        severity_style = "red bold" if f.severity == "error" else "yellow"
        row = []
        if show_connection:
            row.append(f.connection_name)
        row.extend([
            f.check_type,
            f"[{severity_style}]{f.severity}[/{severity_style}]",
            f"{f.schema_name}.{f.table_name}",
            f.description,
        ])
        table.add_row(*row)

    console.print(table)


def print_dbt_findings_table(dbt_findings: list[DbtFinding]) -> None:
    """Render dbt findings as a Rich table to the console."""
    if not dbt_findings:
        return

    table = Table(title="dbt Findings", show_lines=True)
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Severity", width=8)
    table.add_column("Node", style="blue")
    table.add_column("Time (s)", justify="right", width=10)
    table.add_column("Description")

    for f in dbt_findings:
        severity_style = "red bold" if f.severity == "error" else "yellow"
        table.add_row(
            f.resource_type,
            f"[{severity_style}]{f.severity}[/{severity_style}]",
            f.unique_id,
            f"{f.execution_time:.1f}",
            f.description,
        )

    console.print(table)


def print_cost_summary(records: list[CostRecord]) -> None:
    """Render a cost summary as Rich tables to the console.

    Args:
        records: Cost records to summarize. Prints nothing when empty.
    """
    if not records:
        return

    summary = summarize_costs(records)

    console.print(
        f"\n[bold]Estimated BigQuery Cost:[/bold] ${summary['total_cost_usd']:.2f}"
    )

    if summary["top_tables"]:
        table = Table(title="Top Tables by Cost", show_lines=True)
        table.add_column("Table", style="blue")
        table.add_column("Cost (USD)", justify="right")
        for entry in summary["top_tables"]:
            table.add_row(
                f"{entry['schema']}.{entry['table']}",
                f"${entry['cost_usd']:.2f}",
            )
        console.print(table)

    if summary["top_users"]:
        table = Table(title="Top Users by Cost", show_lines=True)
        table.add_column("User", style="blue")
        table.add_column("Cost (USD)", justify="right")
        for entry in summary["top_users"]:
            table.add_row(entry["user"], f"${entry['cost_usd']:.2f}")
        console.print(table)


def print_findings_json(
    findings: list[Finding],
    dbt_findings: list[DbtFinding] | None = None,
    cost_records: list[CostRecord] | None = None,
) -> None:
    """Print findings as JSON to the console."""
    data: dict = {"findings": [asdict(f) for f in findings]}
    if dbt_findings is not None:
        data["dbt_findings"] = [asdict(f) for f in dbt_findings]
    if cost_records:
        data["cost_summary"] = summarize_costs(cost_records)
    console.print(json.dumps(data, indent=2))


def run_check(
    output_json: bool = False,
    verbose: bool = False,
    write_results: bool | None = None,
    connection_name: str | None = None,
) -> None:
    """CLI entry point for ``olly check``.

    Loads config, runs all checks, optionally writes results to disk, and
    prints output as a table or JSON. Exits with code 1 if any findings
    are present.

    Args:
        output_json: If True, print findings as JSON instead of a table.
        verbose: Enable debug logging when True.
        write_results: Override for ``settings.write_results``. When None,
            the config value is used.
        connection_name: Optional connection name to check.
    """
    setup_logging(verbose)
    config = load_config()
    warnings = validate_config(config)
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

    connections = resolve_connections(config, connection_name)
    has_any_snapshots = False
    with open_state(config) as state_db:
        for name, nc in connections:
            if state_db.has_snapshots(connection_name=name):
                has_any_snapshots = True
                break

    if not has_any_snapshots:
        console.print(
            "[yellow]No snapshots found. Run 'olly snapshot' first.[/yellow]"
        )
        raise SystemExit(1)

    findings, dbt_findings, cost_records = run_checks(
        config, connection_name=connection_name
    )
    should_write = (
        config.settings.write_results if write_results is None else write_results
    )
    if should_write:
        write_findings_json(
            findings, dbt_findings=dbt_findings, cost_records=cost_records
        )

    send_slack_alert(config.slack, findings, dbt_findings)

    if output_json:
        print_findings_json(findings, dbt_findings, cost_records)
    else:
        if not findings and not dbt_findings:
            console.print("[bold green]All checks passed.[/bold green]")
        print_findings_table(findings)
        print_dbt_findings_table(dbt_findings)
        print_cost_summary(cost_records)

        if findings or dbt_findings:
            parts = []
            error_count = sum(1 for f in findings if f.severity == "error")
            warn_count = sum(1 for f in findings if f.severity == "warning")
            if findings:
                parts.append(f"{error_count} error(s), {warn_count} warning(s)")
            if dbt_findings:
                dbt_errors = sum(1 for f in dbt_findings if f.severity == "error")
                dbt_warns = sum(1 for f in dbt_findings if f.severity == "warning")
                parts.append(f"{dbt_errors} dbt error(s), {dbt_warns} dbt warning(s)")
            if parts:
                console.print("\n" + " — ".join(parts))

    if findings or dbt_findings:
        sys.exit(1)
