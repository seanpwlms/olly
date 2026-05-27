from __future__ import annotations

import json
import logging
from dataclasses import asdict

from rich.console import Console

from olly.adapter import connect_typed
from olly.checks.usage import check_usage
from olly.config import load_config
from olly.config_ops import resolve_connections, select_schema_names
from olly.logging import setup_logging, setup_query_logging
from olly.cli.check import print_findings_table
from olly.models import Finding

logger = logging.getLogger(__name__)

console = Console()


def run_unused(
    output_json: bool = False,
    verbose: bool = False,
    connection_name: str | None = None,
) -> None:
    """Run usage checks and display unused/stale tables.

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
    connections = resolve_connections(config, connection_name)

    for name, nc in connections:
        backend = connect_typed(nc.connection)
        schemas = select_schema_names(nc.selection, backend.list_schemas())

        usage_config = config.usage
        findings = check_usage(
            backend, schemas, usage_config,
            all_tables=backend.list_tables(schemas),
        )
        for f in findings:
            f.connection_name = name
        all_findings.extend(findings)

    if output_json:
        console.print(
            json.dumps(
                {"findings": [asdict(f) for f in all_findings]}, indent=2
            )
        )
    else:
        if not all_findings:
            console.print("[bold green]No unused or stale tables found.[/bold green]")
        else:
            print_findings_table(all_findings)
            error_count = sum(1 for f in all_findings if f.severity == "error")
            warn_count = sum(1 for f in all_findings if f.severity == "warning")
            console.print(f"\n{error_count} error(s), {warn_count} warning(s)")
