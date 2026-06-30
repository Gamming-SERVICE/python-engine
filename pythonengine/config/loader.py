"""Configuration loading, validation, and startup.txt parsing."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from pythonengine.config.models import (AppConfig, AuthConfig, Config, DefaultsConfig,
                                        EngineConfig, LoggingConfig, SecurityConfig,
                                        WebSocketConfig)

CONFIG_FILE = Path("config.yaml")
STARTUP_FILE = Path("startup.txt")
_SAFE_ID = re.compile(r"[^a-zA-Z0-9_.-]+")


def _merge_dataclass(cls, data: dict[str, Any] | None):
    return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


def app_id_for(path: str) -> str:
    stem = Path(path).stem or "app"
    digest = hashlib.sha1(path.encode(), usedforsecurity=False).hexdigest()[:8]
    return _SAFE_ID.sub("-", f"{stem}-{digest}")


def parse_startup() -> list[str]:
    if not STARTUP_FILE.exists():
        STARTUP_FILE.write_text("# apps/example/main.py\n", encoding="utf-8")
    paths: list[str] = []
    for line in STARTUP_FILE.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        paths.append(clean)
    return paths


def _startup_apps(defaults: DefaultsConfig) -> list[AppConfig]:
    apps: list[AppConfig] = []
    for path in parse_startup():
        app_path = Path(path)
        apps.append(AppConfig(
            id=app_id_for(path), name=app_path.stem, path=path,
            working_directory=str(app_path.parent) if str(app_path.parent) != "." else ".",
            cpu_limit=defaults.cpu_limit, cpu_duration=defaults.cpu_duration,
            ram_limit=defaults.ram_limit, restart_policy=defaults.restart_policy,
            restart_max_retries=defaults.restart_max_retries,
            restart_delay=defaults.restart_delay, restart_backoff=defaults.restart_backoff,
            startup_delay=defaults.startup_delay,
        ))
    return apps


def load_config() -> Config:
    raw: dict[str, Any] = {}
    if CONFIG_FILE.exists():
        raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    defaults = _merge_dataclass(DefaultsConfig, raw.get("defaults"))
    config = Config(
        engine=_merge_dataclass(EngineConfig, raw.get("engine")),
        logging=_merge_dataclass(LoggingConfig, raw.get("logging")),
        authentication=_merge_dataclass(AuthConfig, raw.get("authentication")),
        security=_merge_dataclass(SecurityConfig, raw.get("security")),
        websocket=_merge_dataclass(WebSocketConfig, raw.get("websocket")),
        defaults=defaults,
        raw=raw,
    )
    configured = [AppConfig(**a) for a in raw.get("apps", [])]
    seen = {a.path for a in configured}
    config.apps = configured + [a for a in _startup_apps(defaults) if a.path not in seen]
    Path(config.logging.directory).mkdir(parents=True, exist_ok=True)
    Path(config.engine.database_location).parent.mkdir(parents=True, exist_ok=True)
    return config


def validate_app_path(path: str) -> Path:
    candidate = Path(path).resolve()
    root = Path.cwd().resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("application path must remain inside project directory")
    if not candidate.exists() or candidate.suffix != ".py":
        raise ValueError(f"invalid Python application: {path}")
    return candidate
