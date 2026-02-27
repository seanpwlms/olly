from __future__ import annotations

from pathlib import Path


def run_serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "Dashboard dependencies not installed. "
            "Install with: uv pip install -e '.[dashboard]'"
        )

    dist_dir = Path(__file__).parent.parent / "dashboard" / "static" / "dist"
    if not dist_dir.exists():
        raise SystemExit(
            "Dashboard frontend not built. Run:\n"
            "  cd src/olly/dashboard/frontend && npm install && npm run build"
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
