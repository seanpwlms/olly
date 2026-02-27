from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm

from olly.config import load_config
from olly.state import StateDB

console = Console()


def run_clean(*, yes: bool = False) -> None:
    """CLI entry point for ``olly clean``.

    Deletes the local SQLite state database. Does nothing when state
    is stored in the warehouse (BigQuery, etc.).

    Args:
        yes: Skip confirmation prompt when True.
    """
    config = load_config()
    if config.settings.state_schema:
        console.print(
            "[yellow]State is managed in the warehouse — nothing to clean locally.[/yellow]"
        )
        return

    db = StateDB()
    db_path = db.db_path

    if not db_path.exists():
        db.close()
        console.print("[yellow]No state database found.[/yellow]")
        return

    console.print(f"State database: [bold]{db_path}[/bold]")

    if not yes and not Confirm.ask("Delete this state database?", default=False):
        db.close()
        console.print("Aborted.")
        return

    db.clean()
    console.print(f"[green]Deleted state database at {db_path}[/green]")
