"""Runtime configuration loaded from environment variables and YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """Centralised application settings."""

    host: str = os.getenv("FLASK_HOST", "0.0.0.0")
    port: int = int(os.getenv("FLASK_PORT", "5000"))
    debug: bool = _as_bool(os.getenv("FLASK_DEBUG"), False)
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key")
    database_path: str = os.getenv("DATABASE_PATH", "data/monitor.db")
    config_path: str = os.getenv("CONFIG_PATH", "config.yaml")
    enable_scheduler: bool = _as_bool(os.getenv("ENABLE_SCHEDULER"), True)
    retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))

    @property
    def db_file(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def config_file(self) -> Path:
        path = Path(self.config_path)
        return path if path.is_absolute() else BASE_DIR / path


@dataclass
class TargetSpec:
    """A monitored endpoint definition sourced from YAML."""

    name: str
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    expected_status: int = 200
    timeout: float = 10.0
    interval: int = 60
    enabled: bool = True

    def as_row(self) -> dict[str, Any]:
        import json

        return {
            "name": self.name,
            "url": self.url,
            "method": self.method.upper(),
            "headers": json.dumps(self.headers or {}),
            "body": self.body,
            "expected_status": int(self.expected_status),
            "timeout": float(self.timeout),
            "interval_seconds": int(self.interval),
            "enabled": 1 if self.enabled else 0,
        }


def load_targets(config_file: Path) -> list[TargetSpec]:
    """Parse the YAML config into a list of :class:`TargetSpec`."""
    if not config_file.exists():
        return []

    with config_file.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    defaults = raw.get("defaults", {}) or {}
    targets: list[TargetSpec] = []

    for entry in raw.get("targets", []) or []:
        merged = {**defaults, **entry}
        body = merged.get("body")
        if body is not None and not isinstance(body, str):
            import json

            body = json.dumps(body)
        targets.append(
            TargetSpec(
                name=merged["name"],
                url=merged["url"],
                method=merged.get("method", "GET"),
                headers=merged.get("headers", {}) or {},
                body=body,
                expected_status=merged.get("expected_status", 200),
                timeout=merged.get("timeout", 10),
                interval=merged.get("interval", 60),
                enabled=merged.get("enabled", True),
            )
        )
    return targets


settings = Settings()
