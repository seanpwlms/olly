from __future__ import annotations

from rich.console import Console

from olly.adapter import connect_typed
from olly.config import load_config
from olly.config_ops import resolve_connections

console = Console()


def run_debug(*, connection_name: str | None = None) -> None:
    """Test connectivity to configured warehouses."""
    config = load_config()

    for name, nc in resolve_connections(config, connection_name):
        console.print(f"[bold]Testing connection: {name}[/bold]")
        try:
            adapter = connect_typed(nc.connection)
            schemas = adapter.list_schemas()
            console.print("[green]Connection successful.[/green]")
            console.print(f"  Schemas: {', '.join(schemas) if schemas else '(none)'}")
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            raise SystemExit(1)
