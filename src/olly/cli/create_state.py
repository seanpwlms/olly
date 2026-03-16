"""CLI command to create the warehouse state schema and tables."""

from __future__ import annotations

from rich.console import Console

from olly.config import load_config
from olly.config_ops import resolve_connections
from olly.adapter import connect_typed
from olly.state import open_state
from olly.state.warehouse import WarehouseStateStore, _DIALECTS

console = Console()


def run_create_state(*, connection_name: str | None = None) -> None:
    """Create the warehouse state schema and tables.

    Reads the current ``olly.toml``, resolves the ``state_schema`` setting,
    lists the objects that will be created, and prompts for confirmation.
    """
    config = load_config()
    state_schema = config.settings.state_schema

    if not state_schema:
        console.print(
            "[red]No state_schema configured in olly.toml.[/red]\n"
            "Add [bold]state_schema[/bold] to your [settings] section first:\n\n"
            '  [settings]\n  state_schema = "olly"'
        )
        raise SystemExit(1)

    # Connect to the first matching connection to determine the dialect
    connections = resolve_connections(config, connection_name)
    if not connections:
        console.print("[red]No connections found in olly.toml.[/red]")
        raise SystemExit(1)

    name, nc = connections[0]
    adapter = connect_typed(nc.connection)
    conn_type = nc.connection.type or ""
    dialect = _DIALECTS.get(conn_type, {})
    quote = dialect.get("quote", lambda s: f'"{s}"')

    # List objects to be created
    schema_fqn = quote(state_schema)
    console.print(f"\nThe following objects will be created via connection [bold]{name}[/bold]:\n")
    console.print(f"  Schema: {schema_fqn}")
    console.print("  Tables:")
    for table_name in WarehouseStateStore.TABLE_NAMES:
        console.print(f"    {schema_fqn}.{quote(table_name)}")
    console.print()

    if not console.input("Proceed? [y/N] ").strip().lower().startswith("y"):
        console.print("[dim]Aborted.[/dim]")
        raise SystemExit(0)

    with open_state(config, adapter, create_tables=True):
        pass

    console.print(f"\n[green]State schema created in {schema_fqn}.[/green]")
