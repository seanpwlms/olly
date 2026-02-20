from __future__ import annotations

import logging

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


def take_snapshot(
    config: OllyConfig, connection_name: str | None = None
) -> list[tuple[str, int, int, int]]:
    """Capture the current warehouse state and store it in the state database.

    Args:
        config: Parsed Olly configuration.
        connection_name: Optional connection name to snapshot. When None, all
            connections are snapshotted.

    Returns:
        List of (connection_name, snapshot_id, table_count, column_count) tuples.
    """
    logger.info("Starting snapshot")
    results: list[tuple[str, int, int, int]] = []

    for name, nc in resolve_connections(config, connection_name):
        backend = connect_typed(nc.connection)
        schemas = select_schema_names(nc.selection, backend.list_schemas())
        logger.debug("[%s] Selected schemas: %s", name, schemas)
        tables = backend.fetch_schema_info(schemas)
        tables = filter_table_infos(nc.selection, tables)
        logger.debug("[%s] Filtered to %d tables", name, len(tables))
        volumes = backend.fetch_row_counts(tables)

        with open_state(config, backend, nc.connection.type) as state_db:
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
    results = take_snapshot(config, connection_name=connection_name)

    for name, snapshot_id, table_count, col_count in results:
        if len(results) > 1:
            console.print(f"\n[bold]Connection: {name}[/bold]")
        console.print(f"[green]Snapshot #{snapshot_id} saved.[/green]")
        console.print(f"  Tables: {table_count}")
        console.print(f"  Columns: {col_count}")
