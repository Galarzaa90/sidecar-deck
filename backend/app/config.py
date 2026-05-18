from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_port: int = Field(default=8080, alias="APP_PORT")
    metrics_token: str = Field(default="change-me", alias="METRICS_TOKEN")
    metrics_stale_seconds: int = Field(default=5, alias="METRICS_STALE_SECONDS")
    metrics_offline_seconds: int = Field(default=15, alias="METRICS_OFFLINE_SECONDS")
    history_seconds: int = Field(default=600, alias="HISTORY_SECONDS")
    static_dir: Path = Field(default=Path("/app/static"), alias="STATIC_DIR")


@lru_cache
def get_settings() -> Settings:
    return Settings()
