from __future__ import annotations

import logging
from typing import Any, Sequence

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

from olly.adapter import connect_typed
from olly.config import OllyConfig, load_config
from olly.config_ops import (
    filter_table_infos,
    resolve_connections,
    select_schema_names,
    validate_config,
)
from olly.logging import setup_logging, setup_query_logging
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
            provided, each snapshot step is reported with a progress spinner.

    Returns:
        List of (connection_name, snapshot_id, table_count, column_count) tuples.
    """
    logger.info("Starting snapshot")
    results: list[tuple[str, int, int, int]] = []
    out = progress_console

    for name, nc in resolve_connections(config, connection_name):
        if out:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=out,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    f"Connecting to [bold]{nc.connection.type}[/bold] warehouse...",
                )
                backend = connect_typed(nc.connection)

                progress.update(task, description="Fetching schemas...")
                schemas = select_schema_names(nc.selection, backend.list_schemas())
                logger.debug("[%s] Selected schemas: %s", name, schemas)
                schema_list = ", ".join(schemas) if schemas else "(none)"

                progress.update(
                    task,
                    description=f"Fetching schema info for {len(schemas)} schema(s)...",
                )

            # Schema info — count tables first for a determinate progress bar
            all_table_names = backend.list_tables(schemas)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=20),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=out,
                transient=True,
            ) as progress:
                schema_task = progress.add_task(
                    "Fetching schema info...", total=len(all_table_names)
                )

                def _on_schema_progress(
                    schema: str,
                    table: str,
                    _p: Progress = progress,
                    _t: TaskID = schema_task,
                ) -> None:
                    _p.update(_t, description=f"Schema info: {table}", advance=1)

                tables = backend.fetch_schema_info(schemas, on_progress=_on_schema_progress)
                tables = filter_table_infos(nc.selection, tables)
                logger.debug("[%s] Filtered to %d tables", name, len(tables))

            # Row counts — determinate bar since we know the table count
            non_view_count = sum(1 for t in tables if t.table_type != "VIEW")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=20),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=out,
                transient=True,
            ) as progress:
                count_task = progress.add_task(
                    "Fetching row counts...", total=non_view_count
                )

                def _on_count_progress(
                    schema: str,
                    table: str,
                    _p: Progress = progress,
                    _t: TaskID = count_task,
                ) -> None:
                    _p.update(_t, description=f"Row counts: {table}", advance=1)

                volumes = backend.fetch_row_counts(tables, on_progress=_on_count_progress)

            # Save
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=out,
                transient=True,
            ) as progress:
                progress.add_task("Saving snapshot...")
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
            out.print(
                f"[green]✓[/green] Snapshot #{snapshot_id} saved — "
                f"{len(schemas)} schema(s), {len(tables)} table(s), "
                f"{total_cols} column(s) [{schema_list}]"
            )
        else:
            backend = connect_typed(nc.connection)
            schemas = select_schema_names(nc.selection, backend.list_schemas())
            logger.debug("[%s] Selected schemas: %s", name, schemas)
            tables = backend.fetch_schema_info(schemas)
            tables = filter_table_infos(nc.selection, tables)
            logger.debug("[%s] Filtered to %d tables", name, len(tables))
            volumes = backend.fetch_row_counts(tables)
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
    if config.settings.log_queries:
        setup_query_logging()
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
