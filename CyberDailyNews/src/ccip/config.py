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
    subject: str = "Daily Cyber Intelligence - {{ report_date }}"
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
    source_files: tuple[str, ...] = ()
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
    source_files = raw.get("source_files", [])
    if not isinstance(source_files, list):
        raise ValueError("source_files must be a YAML list")
    merged_sources = list(raw.get("sources", []))
    for source_file in source_files:
        source_path = config_path.parent / source_file
        with source_path.open(encoding="utf-8") as stream:
            source_document = yaml.safe_load(stream) or {}
        if not isinstance(source_document, dict) or not isinstance(
            source_document.get("sources", []), list
        ):
            raise ValueError(f"source file must contain a sources list: {source_path}")
        merged_sources.extend(source_document.get("sources", []))
    raw["sources"] = merged_sources
    names: set[str] = set()
    urls: set[str] = set()
    for source in merged_sources:
        if not isinstance(source, dict):
            raise ValueError("each source must be a YAML mapping")
        name = source.get("name")
        url = source.get("url")
        if isinstance(name, str) and name in names:
            raise ValueError(f"duplicate source name: {name}")
        if isinstance(url, str) and url in urls:
            raise ValueError(f"duplicate source URL: {url}")
        if isinstance(name, str):
            names.add(name)
        if isinstance(url, str):
            urls.add(url)
    _apply_environment_overrides(raw)
    return Settings.model_validate(raw)
