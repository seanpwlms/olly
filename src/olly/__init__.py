import cyclopts

from olly.checker import run_checks

app = cyclopts.App(name="olly", help="Data quality framework for data warehouses.")

__all__ = [
    "run_checks",
]


@app.command
def init() -> None:
    """Run the interactive setup wizard.

    Creates an ``olly.toml`` config file and initializes the state
    database in ``~/.olly/<project-hash>/``.
    """
    from olly.cli.init import run_init

    run_init()


@app.command
def snapshot(*, verbose: bool = False, connection: str | None = None) -> None:
    """Capture a snapshot of the current warehouse state.

    Connects to the configured warehouse, introspects schemas and tables,
    and stores schema info and row counts in the local state database.

    Args:
        verbose: Print detailed progress information.
        connection: Name of a specific connection to snapshot.
    """
    from olly.cli.snapshot import run_snapshot

    run_snapshot(verbose=verbose, connection_name=connection)


@app.command
def check(
    *,
    json: bool = False,
    verbose: bool = False,
    write_results: bool | None = None,
    connection: str | None = None,
) -> None:
    """Run data quality checks against the latest snapshot.

    Compares the most recent snapshot to previous state and reports
    schema changes, volume anomalies, and freshness issues.

    Args:
        json: Emit machine-readable JSON output instead of human-readable text.
        verbose: Print detailed progress information.
        write_results: Persist check results to the state database. Defaults to
            the value in ``olly.toml`` when ``None``.
        connection: Name of a specific connection to check.
    """
    from olly.cli.check import run_check

    run_check(
        output_json=json,
        verbose=verbose,
        write_results=write_results,
        connection_name=connection,
    )


@app.command
def config_explain(*, connection: str | None = None) -> None:
    """Explain which schemas/tables are selected and how overrides resolve.

    Loads the current config and warehouse state, then prints a summary
    showing which schemas and tables match the selection filters and how
    per-table settings are resolved through the override chain.

    Args:
        connection: Name of a specific connection to explain.
    """
    from olly.cli.config_explain import run_config_explain

    run_config_explain(connection_name=connection)


@app.command
def unused(
    *, json: bool = False, verbose: bool = False, connection: str | None = None
) -> None:
    """Show unused and stale tables.

    Queries warehouse access history to identify tables with no recent
    queries, regardless of whether the usage check is enabled in config.

    Args:
        json: Emit machine-readable JSON output instead of human-readable text.
        verbose: Print detailed progress information.
        connection: Name of a specific connection to check.
    """
    from olly.cli.unused import run_unused

    run_unused(output_json=json, verbose=verbose, connection_name=connection)


@app.command
def serve(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Olly web dashboard."""
    from olly.cli.serve import run_serve

    run_serve(host=host, port=port)


@app.command
def serve_prefab(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Olly Prefab dashboard (experimental)."""
    from olly.cli.serve import run_serve_prefab

    run_serve_prefab(host=host, port=port)


@app.command
def debug(*, connection: str | None = None) -> None:
    """Test connectivity to the configured warehouse.

    Connects to the warehouse and lists available schemas to verify
    that credentials and network access are working.

    Args:
        connection: Name of a specific connection to test.
    """
    from olly.cli.debug import run_debug

    run_debug(connection_name=connection)


def main() -> None:
    """Entry point for the ``olly`` CLI."""
    app()
