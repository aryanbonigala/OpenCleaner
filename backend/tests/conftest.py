from __future__ import annotations

from collections.abc import Generator

import pytest

from app.services.settings_service import default_settings


@pytest.fixture
def settings_memory_store(monkeypatch) -> Generator[dict[str, str], None, None]:
    """In-memory settings table for tests (avoids aiosqlite loop conflicts)."""
    store: dict[str, str] = {}

    async def fake_get(key: str, default: str | None = None) -> str | None:
        return store.get(key, default)

    async def fake_set(key: str, value: str) -> None:
        store[key] = value

    for target in (
        "app.db.get_setting",
        "app.db.set_setting",
        "app.services.settings_service.get_setting",
        "app.services.settings_service.set_setting",
    ):
        if "get_setting" in target:
            monkeypatch.setattr(target, fake_get)
        else:
            monkeypatch.setattr(target, fake_set)
    yield store


@pytest.fixture
def safe_settings():
    return default_settings()
