"""Typed configuration models."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

RestartPolicy = Literal["never", "always", "on_failure"]


@dataclass
class EngineConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    startup_delay: float = 2.0
    monitoring_interval: float = 3.0
    shutdown_timeout: float = 10.0
    database_location: str = "data/pythonengine.db"
    timezone: str = "UTC"


@dataclass
class LoggingConfig:
    directory: str = "logs"
    max_bytes: int = 10 * 1024 * 1024
    backups: int = 5


@dataclass
class AuthConfig:
    enabled: bool = True
    username: str = "admin"
    password_hash: str = ""


@dataclass
class SecurityConfig:
    session_secret: str = "change-me"
    csrf_secret: str = "change-me-too"


@dataclass
class WebSocketConfig:
    enabled: bool = True
    max_clients: int = 500


@dataclass
class DefaultsConfig:
    cpu_limit: float = 80.0
    cpu_duration: float = 30.0
    ram_limit: int = 512 * 1024 * 1024
    restart_policy: RestartPolicy = "on_failure"
    restart_max_retries: int = 5
    restart_delay: float = 5.0
    restart_backoff: float = 2.0
    startup_delay: float = 2.0


@dataclass
class AppConfig:
    id: str
    name: str
    path: str
    arguments: list[str] = field(default_factory=list)
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    cpu_limit: float | None = None
    cpu_duration: float | None = None
    ram_limit: int | None = None
    restart_policy: RestartPolicy | None = None
    restart_max_retries: int | None = None
    restart_delay: float | None = None
    restart_backoff: float | None = None
    startup_delay: float | None = None
    health_check_url: str | None = None
    enabled: bool = True
    auto_start: bool = True
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    group: str = "default"
    scheduled_restart: str | None = None


@dataclass
class Config:
    engine: EngineConfig = field(default_factory=EngineConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    authentication: AuthConfig = field(default_factory=AuthConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    apps: list[AppConfig] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return Path.cwd()
