"""Standalone entrypoint for running the backend as a packaged sidecar process.

Importing this module must never start a server; only calling `main()` does.
No scan/cleanup/performance action is triggered here — this only serves the
existing FastAPI app (`app.main:app`) over uvicorn.
"""

from __future__ import annotations

import argparse

import uvicorn

from app.config import get_settings


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the OpenCleaner AI backend sidecar.")
    parser.add_argument("--host", default=settings.host, help=f"default: {settings.host}")
    parser.add_argument("--port", type=int, default=settings.port, help=f"default: {settings.port}")
    args = parser.parse_args(argv)
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
