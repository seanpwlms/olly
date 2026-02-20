from __future__ import annotations


def run_serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "Dashboard dependencies not installed. "
            "Install with: uv pip install -e '.[dashboard]'"
        )

    from olly.dashboard.app import app

    uvicorn.run(app, host=host, port=port)


def run_serve_prefab(host: str = "127.0.0.1", port: int = 8000) -> None:
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "Dashboard dependencies not installed. "
            "Install with: uv pip install -e '.[dashboard]'"
        )

    from olly.dashboard_prefab.app import app

    uvicorn.run(app, host=host, port=port)
