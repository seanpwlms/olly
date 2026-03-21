from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from olly.adapter import connect_typed
from olly.checker import run_checks
from olly.config import load_config
from olly.config_ops import (
    resolve_connections,
    validate_config,
)
from olly.logging import setup_logging, setup_query_logging
from olly.checks.cost import summarize_costs
from olly.models import CostRecord, DbtFinding, Finding
from olly.results import write_findings_json
from olly.slack import send_slack_alert
from olly.state import open_state

logger = logging.getLogger(__name__)

console = Console()

ALL_CHECK_TYPES = frozenset(
    {"schema", "volume", "freshness", "usage", "cost", "contracts", "integrity", "dbt"}
)
SNAPSHOT_CHECK_TYPES = frozenset({"schema", "volume", "freshness", "contracts"})
PER_CONNECTION_CHECK_TYPES = frozenset(
    {"schema", "volume", "freshness", "usage", "cost", "contracts"}
)
GLOBAL_CHECK_TYPES = frozenset({"integrity", "dbt"})


def _build_check_table(
    findings: list[Finding], title: str,
) -> Table:
    """Build a Rich table for findings that share a single check type."""
    table = Table(title=title, show_lines=False, pad_edge=True, padding=(0, 1))
    table.add_column("Severity", width=8)
    table.add_column("Table", style="blue")
    table.add_column("Description")

    for f in findings:
        severity_style = "red bold" if f.severity == "error" else "yellow"
        table.add_row(
            f"[{severity_style}]{f.severity}[/{severity_style}]",
            f"{f.schema_name}.{f.table_name}",
            f.description,
        )
    return table


def _print_findings_group(
    findings: list[Finding], prefix: str = "",
) -> None:
    """Print one table per check type, with an optional title prefix."""
    by_check: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=lambda f: f.check_type):
        by_check.setdefault(f.check_type, []).append(f)

    for check_type, check_findings in by_check.items():
        title = f"{prefix}{check_type}" if prefix else check_type
        console.print(_build_check_table(check_findings, title=title))
        console.print()


def print_findings_table(findings: list[Finding]) -> None:
    """Render findings as Rich tables to the console.

    Findings are split by connection (if multiple) and check type so that
    neither occupies a column — each combination gets its own table.

    Args:
        findings: List of findings to display. Prints nothing when empty.
    """
    if not findings:
        return

    show_connection = any(f.connection_name for f in findings)

    if not show_connection:
        _print_findings_group(findings)
        return

    by_connection: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=lambda f: f.connection_name):
        by_connection.setdefault(f.connection_name, []).append(f)

    for conn_name, conn_findings in by_connection.items():
        _print_findings_group(conn_findings, prefix=f"{conn_name} — ")


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


def _parse_select(select: str | None) -> set[str] | None:
    """Parse a comma-separated check type string into a validated set.

    Returns None when *select* is None (meaning run all checks).

    Raises:
        SystemExit: If any requested check type is not recognised.
    """
    if select is None:
        return None
    types = {t.strip() for t in select.split(",") if t.strip()}
    unknown = types - ALL_CHECK_TYPES
    if unknown:
        sorted_unknown = ", ".join(sorted(unknown))
        sorted_valid = ", ".join(sorted(ALL_CHECK_TYPES))
        console.print(
            f"[red]Unknown check type(s): {sorted_unknown}[/red]\n"
            f"Valid types: {sorted_valid}"
        )
        raise SystemExit(1)
    return types


def run_check(
    output_json: bool = False,
    verbose: bool = False,
    write_results: bool | None = None,
    connection_name: str | None = None,
    select: str | None = None,
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
        select: Comma-separated list of check types to run.
    """
    setup_logging(verbose)
    select_checks = _parse_select(select)
    config = load_config()
    if config.settings.log_queries:
        setup_query_logging()
    warnings = validate_config(config)
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

    needs_connections = select_checks is None or bool(
        select_checks & PER_CONNECTION_CHECK_TYPES
    )
    needs_snapshots = select_checks is None or bool(
        select_checks & SNAPSHOT_CHECK_TYPES
    )

    connections = resolve_connections(config, connection_name) if needs_connections else []

    if needs_snapshots and connections:
        has_multiple_snapshots = False
        # Connect to the first adapter so open_state can route to warehouse
        # when state_schema is configured.
        first_adapter = None
        if config.settings.state_schema and connections:
            first_adapter = connect_typed(connections[0][1].connection)
        with open_state(config, first_adapter) as state_db:
            for name, nc in connections:
                if state_db.has_multiple_snapshots(connection_name=name):
                    has_multiple_snapshots = True
                    break

        if not has_multiple_snapshots:
            console.print(
                "[yellow]Need at least 2 snapshots to run checks. Run 'olly snapshot' twice.[/yellow]"
            )
            raise SystemExit(1)

    # Count total check steps for the progress bar
    num_connections = len(connections)
    # Per connection: connect, schema, volume, freshness
    per_conn = 1  # connect
    if select_checks is None or "schema" in select_checks:
        per_conn += 1
    if select_checks is None or "volume" in select_checks:
        per_conn += 1
    if select_checks is None or "freshness" in select_checks:
        per_conn += 1
    if (select_checks is None or "usage" in select_checks) and config.usage.enabled:
        per_conn += 1
    if (select_checks is None or "cost" in select_checks) and config.usage.cost_enabled:
        per_conn += 1
    if (select_checks is None or "contracts" in select_checks) and config.contracts.module:
        per_conn += 1
    total_steps = num_connections * per_conn
    # Global: dbt + saving (always), integrity (if configured)
    total_steps += 2
    if (select_checks is None or "integrity" in select_checks) and config.integrity.module:
        total_steps += 1

    show_connection = num_connections > 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=20),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            "Running checks...", total=total_steps, visible=False,
        )

        def _on_progress(
            conn: str,
            check: str,
            _p: Progress = progress,
            _t: TaskID = task,
        ) -> None:
            label = f"{conn} — {check}" if conn and show_connection else check
            _p.update(_t, description=label, advance=1, visible=True)

        findings, dbt_findings, cost_records = run_checks(
            config, connection_name=connection_name, on_progress=_on_progress,
            select_checks=select_checks,
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
