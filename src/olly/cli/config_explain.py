from __future__ import annotations

from rich.console import Console

from olly.adapter import connect_typed
from olly.config import load_config
from olly.config_ops import resolve_connections
from olly.explain import explain_config, format_explain

console = Console()


def run_config_explain(connection_name: str | None = None) -> None:
    """CLI entry point for ``olly config explain``.

    Loads the config, connects to the warehouse, and prints a human-readable
    breakdown of which schemas and tables are selected and how settings
    resolve for each table.
    """
    config = load_config()
    connections = resolve_connections(config, connection_name)
    backends = {name: connect_typed(nc.connection) for name, nc in connections}
    result = explain_config(config, backends, connection_name=connection_name)
    console.print(format_explain(result))
