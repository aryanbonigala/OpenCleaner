"""Sidecar entrypoint contract: import is inert, main() serves the existing app on loopback."""

from __future__ import annotations

import importlib
from unittest.mock import patch

from app import sidecar
from app.config import get_settings


def test_import_does_not_start_server():
    with patch("uvicorn.run") as mock_run:
        importlib.reload(sidecar)
    mock_run.assert_not_called()


def test_main_uses_config_defaults():
    from app.main import app as fastapi_app

    settings = get_settings()
    with patch("app.sidecar.uvicorn.run") as mock_run:
        sidecar.main([])
    mock_run.assert_called_once_with(fastapi_app, host=settings.host, port=settings.port)
    assert settings.host == "127.0.0.1"


def test_main_accepts_host_and_port_overrides():
    from app.main import app as fastapi_app

    with patch("app.sidecar.uvicorn.run") as mock_run:
        sidecar.main(["--host", "0.0.0.0", "--port", "9999"])
    mock_run.assert_called_once_with(fastapi_app, host="0.0.0.0", port=9999)


def test_import_does_not_import_app_main():
    import sys

    sys.modules.pop("app.main", None)
    importlib.reload(sidecar)
    assert "app.main" not in sys.modules
