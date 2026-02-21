from __future__ import annotations

from rich.console import Console

from olly.adapter import Adapter, connect_typed
from olly.config import load_config
from olly.config_ops import resolve_connections
from olly.explain import explain_config, format_explain
from olly.logging import setup_logging

console = Console()


def run_config_explain(connection_name: str | None = None) -> None:
    """CLI entry point for ``olly config explain``.

    Loads the config, connects to the warehouse, and prints a human-readable
    breakdown of which schemas and tables are selected and how settings
    resolve for each table.
    """
    setup_logging()
    config = load_config()
    connections = resolve_connections(config, connection_name)
    backends: dict[str, Adapter] = {}
    for name, nc in connections:
        try:
            backends[name] = connect_typed(nc.connection)
        except Exception as e:
            console.print(
                f"[yellow]Could not connect to '{name}': {e}. "
                "Showing config-only output.[/yellow]\n"
            )
    result = explain_config(config, backends, connection_name=connection_name)
    console.print(format_explain(result))
