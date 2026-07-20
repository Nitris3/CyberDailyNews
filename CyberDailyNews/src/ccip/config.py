"""Validated YAML configuration loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppConfig(StrictModel):
    environment: str = "development"
    log_level: str = "INFO"


class DatabaseConfig(StrictModel):
    url: str = "sqlite:///data/ccip.db"
    echo: bool = False


class SMTPConfig(StrictModel):
    host: str
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = None
    password: SecretStr | None = None
    start_tls: bool = True
    timeout_seconds: float = Field(default=30, gt=0)


class EmailConfig(StrictModel):
    sender: str
    recipients: tuple[str, ...]
    subject: str = "CSAA Daily Cyber News - {{ report_date }}"
    smtp: SMTPConfig

    @field_validator("recipients")
    @classmethod
    def recipients_are_not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one email recipient is required")
        return value


class SourceConfig(StrictModel):
    name: str
    kind: Literal["rss", "api", "web"]
    url: str
    category: str
    priority: int = Field(default=3, ge=1, le=5)
    enabled: bool = True


class Settings(StrictModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    email: EmailConfig
    sources: tuple[SourceConfig, ...] = ()


def _apply_environment_overrides(data: dict[str, Any]) -> None:
    """Apply secrets without requiring credentials in YAML."""
    smtp = data.setdefault("email", {}).setdefault("smtp", {})
    mappings = {
        "CCIP_SMTP_HOST": "host",
        "CCIP_SMTP_USERNAME": "username",
        "CCIP_SMTP_PASSWORD": "password",
    }
    for environment_name, config_name in mappings.items():
        if value := os.getenv(environment_name):
            smtp[config_name] = value


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a YAML mapping")
    _apply_environment_overrides(raw)
    return Settings.model_validate(raw)

