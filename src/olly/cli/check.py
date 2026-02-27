from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict

from rich.console import Console
from rich.table import Table

from olly.checker import run_checks
from olly.config import load_config
from olly.config_ops import (
    resolve_connections,
    validate_config,
)
from olly.logging import setup_logging
from olly.checks.cost import summarize_costs
from olly.models import CostRecord, DbtFinding, Finding
from olly.results import write_findings_json
from olly.slack import send_slack_alert
from olly.state import open_state

logger = logging.getLogger(__name__)

console = Console()


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
    """Render dbt findings as a Rich table to the console.

    Only shows issues (non-pass findings). Pass findings are excluded.
    """
    issues = [f for f in dbt_findings if f.severity != "pass"]
    if not issues:
        return

    table = Table(title="dbt Findings", show_lines=True)
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Severity", width=8)
    table.add_column("Node", style="blue")
    table.add_column("Time (s)", justify="right", width=10)
    table.add_column("Description")

    for f in issues:
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
    has_multiple_snapshots = False
    with open_state(config) as state_db:
        for name, nc in connections:
            if state_db.has_multiple_snapshots(connection_name=name):
                has_multiple_snapshots = True
                break

    if not has_multiple_snapshots:
        console.print(
            "[yellow]Need at least 2 snapshots to run checks. Run 'olly snapshot' twice.[/yellow]"
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

    dbt_issues = [f for f in dbt_findings if f.severity != "pass"]

    if output_json:
        print_findings_json(findings, dbt_findings, cost_records)
    else:
        if not findings and not dbt_issues:
            console.print("[bold green]All checks passed.[/bold green]")
        print_findings_table(findings)
        print_dbt_findings_table(dbt_findings)
        print_cost_summary(cost_records)

        if findings or dbt_issues:
            parts = []
            error_count = sum(1 for f in findings if f.severity == "error")
            warn_count = sum(1 for f in findings if f.severity == "warning")
            if findings:
                parts.append(f"{error_count} error(s), {warn_count} warning(s)")
            if dbt_issues:
                dbt_errors = sum(1 for f in dbt_issues if f.severity == "error")
                dbt_warns = sum(1 for f in dbt_issues if f.severity == "warning")
                parts.append(f"{dbt_errors} dbt error(s), {dbt_warns} dbt warning(s)")
            if parts:
                console.print("\n" + " — ".join(parts))

    if findings or dbt_issues:
        sys.exit(1)
