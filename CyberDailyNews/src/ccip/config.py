"""Validated YAML configuration loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppConfig(StrictModel):
    environment: str = "development"
    log_level: str = "INFO"


class DatabaseConfig(StrictModel):
    url: str = "sqlite:///data/ccip.db"
    echo: bool = False


class SummarizationConfig(StrictModel):
    provider: Literal["rules", "ollama"] = "rules"
    model: str = "llama3.2:3b"
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: float = Field(default=60, gt=0)
    fallback_to_rules: bool = True
    audience: str = "senior executives and business leaders"
    instructions: str = (
        "Use plain language. Focus on business impact, urgency, and the action or decision "
        "leaders need to understand. Avoid unnecessary technical detail."
    )


class ScoringConfig(StrictModel):
    priority_multiplier: float = Field(default=1.2, ge=0)
    known_exploited_bonus: float = Field(default=2.0, ge=0)
    ransomware_bonus: float = Field(default=1.5, ge=0)
    critical_keyword_bonus: float = Field(default=1.0, ge=0)
    exploited_keywords: tuple[str, ...] = ("exploited vulnerabilit", "known exploited")
    ransomware_keywords: tuple[str, ...] = ("ransomware",)
    critical_keywords: tuple[str, ...] = ("critical", "remote code execution", "zero-day")
    medium_threshold: float = Field(default=4.0, ge=0)
    high_threshold: float = Field(default=7.0, ge=0)
    critical_threshold: float = Field(default=9.0, ge=0)
    max_score: float = Field(default=10.0, gt=0)
    watchlist_keywords: tuple[str, ...] = ()
    watchlist_bonus: float = Field(default=1.0, ge=0, le=10)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> ScoringConfig:
        if not (
            self.medium_threshold < self.high_threshold < self.critical_threshold <= self.max_score
        ):
            raise ValueError("severity thresholds must increase and cannot exceed max_score")
        return self


class Microsoft365CopilotConfig(StrictModel):
    tenant_id: str = ""
    client_id: str = ""
    enabled: bool = False


class ScheduleConfig(StrictModel):
    enabled: bool = False
    daily_time: str = "08:00"

    @field_validator("daily_time")
    @classmethod
    def daily_time_is_valid(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("daily_time must use 24-hour HH:MM format")
        return value


class CollectionConfig(StrictModel):
    max_workers: int = Field(default=8, ge=1, le=32)
    source_timeout_seconds: float = Field(default=10, gt=0, le=120)
    kev_cache_hours: float = Field(default=6, ge=0, le=168)


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
    template_directory: str = "templates/email"
    html_template: str = "daily_news.html.j2"
    text_template: str = "daily_news.txt.j2"
    max_items: int = Field(default=25, ge=1, le=200)
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
    summarization: SummarizationConfig = SummarizationConfig()
    scoring: ScoringConfig = ScoringConfig()
    microsoft_365_copilot: Microsoft365CopilotConfig = Microsoft365CopilotConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    collection: CollectionConfig = CollectionConfig()
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
