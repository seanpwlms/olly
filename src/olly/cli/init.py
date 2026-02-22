from __future__ import annotations

from pathlib import Path

from rich.console import Console

from olly.config import (
    ConnectionConfig,
    NamedConnection,
    OllyConfig,
    Selection,
    Settings,
    write_config,
)
from olly.adapter import connect_typed
from olly.state import get_olly_dir, open_state

console = Console()

_ADAPTER_TYPES = ["duckdb", "postgres", "bigquery", "snowflake"]


def run_init() -> None:
    """Interactive setup wizard for Olly.

    Prompts the user for connection type and type-specific fields,
    validates the connection, writes ``olly.toml``, and initializes
    the ``~/.olly/<project-hash>/state.db`` state database.
    """
    console.print("[bold]olly init[/bold] — set up data quality monitoring\n")

    # Prompt for adapter type
    console.print(f"Supported types: {', '.join(_ADAPTER_TYPES)}")
    conn_type = console.input("Connection type: ").strip().lower()
    if conn_type not in _ADAPTER_TYPES:
        console.print(
            f"[red]Unknown type '{conn_type}'. Must be one of {_ADAPTER_TYPES}.[/red]"
        )
        raise SystemExit(1)

    conn = _prompt_connection(conn_type)

    nc = NamedConnection(
        name="primary", connection=conn, selection=Selection()
    )
    config = OllyConfig(
        connections={"primary": nc}, settings=Settings()
    )

    # Validate connection (skip for remote warehouses that need credentials)
    adapter = None
    if conn_type in ("bigquery", "snowflake"):
        console.print(
            "[dim]Skipping connection check — will validate on first snapshot.[/dim]\n"
        )
    else:
        try:
            adapter = connect_typed(conn)
            console.print("[green]Connection successful.[/green]\n")
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            raise SystemExit(1)

    # Write config
    config_path = Path("olly.toml")
    write_config(config, config_path)
    console.print(f"\n[green]Wrote {config_path}[/green]")

    # Initialize state store
    with open_state(config, adapter):
        pass  # initialization happens in constructor
    if config.settings.state_schema:
        console.print(
            f"[green]Initialized warehouse state in {config.settings.state_schema}[/green]"
        )
    else:
        state_path = get_olly_dir() / "state.db"
        console.print(f"[green]Initialized {state_path}[/green]")

    console.print("\n[bold green]Done![/bold green] Next steps:")
    console.print("  1. Run [bold]olly snapshot[/bold] to capture baseline")
    console.print("  2. Run [bold]olly check[/bold] to detect changes")


def _prompt_connection(conn_type: str) -> ConnectionConfig:
    """Prompt for type-specific connection fields."""
    if conn_type == "duckdb":
        path = console.input(
            "Path to DuckDB file [dim](leave blank for in-memory)[/dim]: "
        ).strip()
        return ConnectionConfig(type="duckdb", path=path or None)
    if conn_type == "postgres":
        url = console.input(
            "Postgres URL [dim](e.g. postgresql://user:pass@host:5432/db)[/dim]: "
        ).strip()
        if not url:
            console.print("[red]URL is required.[/red]")
            raise SystemExit(1)
        return ConnectionConfig(type="postgres", url=url)
    if conn_type == "bigquery":
        project = console.input("GCP project ID: ").strip()
        if not project:
            console.print("[red]Project ID is required.[/red]")
            raise SystemExit(1)
        dataset = (
            console.input("Default dataset [dim](optional)[/dim]: ").strip() or None
        )
        region = (
            console.input("Region [dim](default: us)[/dim]: ").strip() or None
        )
        return ConnectionConfig(
            type="bigquery", project=project, dataset=dataset, region=region
        )
    # snowflake
    account = console.input("Snowflake account: ").strip()
    if not account:
        console.print("[red]Account is required.[/red]")
        raise SystemExit(1)
    database = console.input("Default database [dim](optional)[/dim]: ").strip() or None
    user = console.input("User [dim](optional)[/dim]: ").strip() or None
    role = console.input("Role [dim](optional)[/dim]: ").strip() or None
    warehouse = console.input("Warehouse [dim](optional)[/dim]: ").strip() or None
    extras: dict[str, str] = {}
    if user:
        extras["user"] = user
    if role:
        extras["role"] = role
    if warehouse:
        extras["warehouse"] = warehouse
    return ConnectionConfig(
        type="snowflake", account=account, database=database, extras=extras
    )
