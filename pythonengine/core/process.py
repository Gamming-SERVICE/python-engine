"""Subprocess lifecycle management."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil

from pythonengine.config.loader import validate_app_path
from pythonengine.config.models import AppConfig, DefaultsConfig
from pythonengine.database.store import Database
from pythonengine.logging.logs import LogService


@dataclass
class AppState:
    config: AppConfig
    pid: int | None = None
    status: str = "stopped"
    start_time: float | None = None
    restart_count: int = 0
    cpu: float = 0.0
    ram: int = 0
    threads: int = 0
    open_files: int = 0
    disk_read: int = 0
    disk_write: int = 0
    net_sent: int = 0
    net_recv: int = 0
    exit_code: int | None = None
    last_error: str | None = None
    command_line: list[str] = field(default_factory=list)

    def uptime(self) -> float:
        return time.time() - self.start_time if self.start_time else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["uptime"] = self.uptime()
        data["log_path"] = f"logs/{self.config.id}.log"
        return data


class ProcessManager:
    def __init__(self, apps: list[AppConfig], defaults: DefaultsConfig, logs: LogService, db: Database) -> None:
        self.defaults = defaults
        self.logs = logs
        self.db = db
        self.apps = {a.id: AppState(a) for a in apps}
        self.processes: dict[str, subprocess.Popen[bytes]] = {}

    def get(self, app_id: str) -> AppState:
        if app_id not in self.apps:
            raise KeyError("unknown application")
        return self.apps[app_id]

    def start(self, app_id: str) -> AppState:
        state = self.get(app_id)
        if state.status == "running" and state.pid:
            return state
        path = validate_app_path(state.config.path)
        cwd = Path(state.config.working_directory or path.parent).resolve()
        env = os.environ.copy() | state.config.environment
        cmd = [sys.executable, str(path), *state.config.arguments]
        log_path = self.logs.app_log(app_id)
        self.logs.rotate(log_path)
        handle = log_path.open("ab", buffering=0)
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=handle, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        self.processes[app_id] = proc
        state.pid = proc.pid
        state.status = "starting"
        state.start_time = time.time()
        state.exit_code = None
        state.command_line = cmd
        time.sleep(0.25)
        state.status = "running" if proc.poll() is None else "failed"
        state.exit_code = proc.poll()
        self.db.event("info", f"Started {state.config.name} pid={state.pid}", app_id)
        return state

    def stop(self, app_id: str, kill: bool = False) -> AppState:
        state = self.get(app_id)
        proc = self.processes.get(app_id)
        if proc and proc.poll() is None:
            try:
                if kill:
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGTERM) if hasattr(os, "killpg") else proc.terminate()
                proc.wait(timeout=10)
            except Exception as exc:
                state.last_error = str(exc)
                proc.kill()
        state.exit_code = proc.poll() if proc else state.exit_code
        state.status = "killed" if kill else "stopped"
        state.pid = None
        self.db.event("warning" if kill else "info", f"{state.status.title()} {state.config.name}", app_id)
        return state

    def restart(self, app_id: str, reason: str = "manual") -> AppState:
        state = self.get(app_id)
        self.stop(app_id)
        state.restart_count += 1
        self.db.conn.execute("INSERT INTO restarts(app_id, reason, count) VALUES(?,?,?)", (app_id, reason, state.restart_count))
        self.db.conn.commit()
        return self.start(app_id)

    def snapshot(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.apps.values()]
