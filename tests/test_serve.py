import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from olly.cli.serve import run_serve


def test_run_serve_missing_uvicorn():
    """Missing uvicorn raises SystemExit with install message."""
    with patch.dict(sys.modules, {"uvicorn": None}):
        with pytest.raises(SystemExit, match="Dashboard dependencies not installed"):
            run_serve()


def test_run_serve_calls_uvicorn():
    """With uvicorn available, calls uvicorn.run with app, host, port."""
    mock_uvicorn = MagicMock()
    mock_app = MagicMock()

    dashboard_mod = ModuleType("olly.dashboard")
    app_mod = ModuleType("olly.dashboard.app")
    app_mod.app = mock_app  # type: ignore[attr-defined]

    with patch.dict(
        sys.modules,
        {
            "uvicorn": mock_uvicorn,
            "olly.dashboard": dashboard_mod,
            "olly.dashboard.app": app_mod,
        },
    ):
        run_serve(host="0.0.0.0", port=9000)

    mock_uvicorn.run.assert_called_once_with(mock_app, host="0.0.0.0", port=9000)
