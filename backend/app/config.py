from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENCLEANER_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".opencleaner"
    db_path: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8742
    cors_origins: list[str] = ["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"]

    telemetry_enabled: bool = False

    @property
    def database_path(self) -> Path:
        if self.db_path is not None:
            return self.db_path
        return self.data_dir / "opencleaner.db"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_dir / "quarantine"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


def get_settings() -> Settings:
    return Settings()
