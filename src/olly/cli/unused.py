from __future__ import annotations

import json
import logging
from dataclasses import asdict

from rich.console import Console
from rich.table import Table

from olly.adapter import connect_typed
from olly.checks.usage import (
    build_usage_findings,
    classify_table_usage,
    summarize_schema_usage,
)
from olly.config import load_config
from olly.config_ops import resolve_connections, select_schema_names
from olly.logging import setup_logging, setup_query_logging
from olly.cli.check import print_findings_table
from olly.models import Finding, SchemaUsageSummary

logger = logging.getLogger(__name__)

console = Console()


def _summary_dict(summary: SchemaUsageSummary, connection_name: str) -> dict:
    """JSON-serializable dict for a schema usage summary."""
    data = asdict(summary)
    data["last_activity_at"] = (
        summary.last_activity_at.isoformat() if summary.last_activity_at else None
    )
    data["connection_name"] = connection_name
    return data


def print_schema_summary(
    summaries: list[SchemaUsageSummary], prefix: str = "",
) -> None:
    """Render a per-schema usage summary as a Rich table.

    Only schemas containing at least one inactive table are shown; prints
    nothing when every schema is fully active.
    """
    inactive = [s for s in summaries if s.stale_count + s.unused_count > 0]
    if not inactive:
        return

    table = Table(title=f"{prefix}Schema Summary", show_lines=False)
    table.add_column("Schema", style="cyan")
    table.add_column("Tables", justify="right")
    table.add_column("Active", justify="right")
    table.add_column("Stale", justify="right")
    table.add_column("Unused", justify="right")
    table.add_column("% Inactive", justify="right")
    table.add_column("Last Activity")

    for s in inactive:
        pct = f"{s.inactive_pct:.0f}%"
        if s.fully_inactive:
            pct = f"[bold red]{pct}[/bold red]"
        table.add_row(
            s.schema_name,
            str(s.total_tables),
            str(s.active_count),
            str(s.stale_count),
            str(s.unused_count),
            pct,
            (
                s.last_activity_at.strftime("%Y-%m-%d")
                if s.last_activity_at
                else "—"
            ),
        )

    console.print(table)
    console.print()


def run_unused(
    output_json: bool = False,
    verbose: bool = False,
    connection_name: str | None = None,
) -> None:
    """Run usage checks and display unused/stale schemas and tables.

    Auto-enables the usage check regardless of config since the user
    explicitly asked for it via ``olly unused``.

    Args:
        output_json: If True, print findings as JSON instead of a table.
        verbose: Enable debug logging when True.
        connection_name: Optional connection name to check.
    """
    setup_logging(verbose)
    config = load_config()
    if config.settings.log_queries:
        setup_query_logging()

    all_findings: list[Finding] = []
    all_summaries: list[tuple[str, list[SchemaUsageSummary]]] = []
    connections = resolve_connections(config, connection_name)

    for name, nc in connections:
        backend = connect_typed(nc.connection)
        schemas = select_schema_names(nc.selection, backend.list_schemas())

        statuses = classify_table_usage(
            backend, schemas, config.usage,
            all_tables=backend.list_tables(schemas),
        )
        findings = build_usage_findings(statuses, config.usage)
        for f in findings:
            f.connection_name = name
        all_findings.extend(findings)
        all_summaries.append((name, summarize_schema_usage(statuses)))

    if output_json:
        print(
            json.dumps(
                {
                    "findings": [asdict(f) for f in all_findings],
                    "schema_summaries": [
                        _summary_dict(s, name)
                        for name, summaries in all_summaries
                        for s in summaries
                    ],
                },
                indent=2,
            )
        )
    else:
        if not all_findings:
            console.print("[bold green]No unused or stale tables found.[/bold green]")
        else:
            show_prefix = len(all_summaries) > 1
            for name, summaries in all_summaries:
                prefix = f"{name} — " if show_prefix else ""
                print_schema_summary(summaries, prefix=prefix)
            print_findings_table(all_findings)
            error_count = sum(1 for f in all_findings if f.severity == "error")
            warn_count = sum(1 for f in all_findings if f.severity == "warning")
            console.print(f"\n{error_count} error(s), {warn_count} warning(s)")
