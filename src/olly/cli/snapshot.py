from __future__ import annotations

import logging
from typing import Any, Sequence

from rich.console import Console

from olly.adapter import connect_typed
from olly.config import OllyConfig, load_config
from olly.config_ops import (
    filter_table_infos,
    resolve_connections,
    select_schema_names,
    validate_config,
)
from olly.logging import setup_logging
from olly.state import open_state

logger = logging.getLogger(__name__)

console = Console()

_MAX_TABLE_NAMES = 8


def _table_list(tables: Sequence[Any], attr: str = "table_name") -> str:
    """Format a short comma-separated list of table names, truncating if needed."""
    names = [getattr(t, attr) for t in tables]
    if len(names) <= _MAX_TABLE_NAMES:
        return ", ".join(names)
    return ", ".join(names[:_MAX_TABLE_NAMES]) + f", ... (+{len(names) - _MAX_TABLE_NAMES} more)"


def take_snapshot(
    config: OllyConfig,
    connection_name: str | None = None,
    progress_console: Console | None = None,
) -> list[tuple[str, int, int, int]]:
    """Capture the current warehouse state and store it in the state database.

    Args:
        config: Parsed Olly configuration.
        connection_name: Optional connection name to snapshot. When None, all
            connections are snapshotted.
        progress_console: Optional Rich console for progress output. When
            provided, each snapshot step is reported with a status spinner.

    Returns:
        List of (connection_name, snapshot_id, table_count, column_count) tuples.
    """
    logger.info("Starting snapshot")
    results: list[tuple[str, int, int, int]] = []
    out = progress_console

    for name, nc in resolve_connections(config, connection_name):
        if out:
            out.print(f"Connecting to [bold]{nc.connection.type}[/bold] warehouse...")
        backend = connect_typed(nc.connection)
        if out:
            out.print("[green]✓[/green] Connected")

        if out:
            out.print("Fetching schemas...")
        schemas = select_schema_names(nc.selection, backend.list_schemas())
        logger.debug("[%s] Selected schemas: %s", name, schemas)
        if out:
            schema_list = ", ".join(schemas) if schemas else "(none)"
            out.print(
                f"[green]✓[/green] Found {len(schemas)} schema(s): {schema_list}"
            )

        if out:
            out.print("Fetching schema info...")
        tables = backend.fetch_schema_info(schemas)
        tables = filter_table_infos(nc.selection, tables)
        logger.debug("[%s] Filtered to %d tables", name, len(tables))
        if out:
            out.print(
                f"[green]✓[/green] {len(tables)} table(s): {_table_list(tables)}"
            )

        if out:
            out.print("Fetching row counts...")
        volumes = backend.fetch_row_counts(tables)
        if out:
            out.print("[green]✓[/green] Row counts collected")

        if out:
            out.print("Saving snapshot...")
        with open_state(config, backend) as state_db:
            snapshot_id = state_db.create_snapshot(connection_name=name)
            state_db.store_schema_data(snapshot_id, tables)
            state_db.store_volume_data(snapshot_id, volumes)
            state_db.prune_old_snapshots(
                config.settings.history_depth, connection_name=name
            )

        total_cols = sum(len(t.columns) for t in tables)
        logger.info(
            "[%s] Snapshot #%d complete: %d tables, %d columns",
            name,
            snapshot_id,
            len(tables),
            total_cols,
        )
        if out:
            out.print(
                f"[green]✓[/green] Snapshot #{snapshot_id} saved "
                f"({len(tables)} tables, {total_cols} columns)"
            )
        results.append((name, snapshot_id, len(tables), total_cols))

    return results


def run_snapshot(
    verbose: bool = False, connection_name: str | None = None
) -> None:
    """CLI entry point for ``olly snapshot``.

    Loads config, takes a snapshot, and prints a summary to the console.

    Args:
        verbose: Enable debug logging when True.
        connection_name: Optional connection name to snapshot.
    """
    setup_logging(verbose)
    config = load_config()
    warnings = validate_config(config)
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    results = take_snapshot(
        config, connection_name=connection_name, progress_console=console
    )

    for name, snapshot_id, table_count, col_count in results:
        if len(results) > 1:
            console.print(f"\n[bold]Connection: {name}[/bold]")
        console.print(f"[green]Snapshot #{snapshot_id} saved.[/green]")
        console.print(f"  Tables: {table_count}")
        console.print(f"  Columns: {col_count}")
