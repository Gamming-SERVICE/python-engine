"""Asynchronous resource and policy monitoring."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import psutil

from pythonengine.core.process import ProcessManager
from pythonengine.database.store import Database


class MonitorService:
    def __init__(self, manager: ProcessManager, db: Database, interval: float) -> None:
        self.manager = manager
        self.db = db
        self.interval = interval
        self.running = False
        self.cpu_over_since: dict[str, float] = defaultdict(float)

    async def run(self) -> None:
        self.running = True
        while self.running:
            await asyncio.to_thread(self.poll_once)
            await asyncio.sleep(self.interval)

    def poll_once(self) -> None:
        for app_id, state in self.manager.apps.items():
            proc = self.manager.processes.get(app_id)
            if not proc:
                continue
            if proc.poll() is not None:
                if state.status == "running":
                    state.exit_code = proc.returncode
                    state.status = "failed" if proc.returncode else "stopped"
                    self.db.event("error", f"{state.config.name} exited with {proc.returncode}", app_id)
                    if self._should_restart(state.config.restart_policy, proc.returncode, state):
                        self.manager.restart(app_id, "policy")
                continue
            try:
                p = psutil.Process(proc.pid)
                state.cpu = p.cpu_percent(interval=None)
                mem = p.memory_info()
                state.ram = mem.rss
                state.threads = p.num_threads()
                state.open_files = len(p.open_files()) if hasattr(p, "open_files") else 0
                io = p.io_counters() if hasattr(p, "io_counters") else None
                state.disk_read = getattr(io, "read_bytes", 0) if io else 0
                state.disk_write = getattr(io, "write_bytes", 0) if io else 0
                self.db.conn.execute("INSERT INTO resource_history(app_id,cpu,ram,threads,files,disk_read,disk_write,net_sent,net_recv) VALUES(?,?,?,?,?,?,?,?,?)",
                                     (app_id, state.cpu, state.ram, state.threads, state.open_files, state.disk_read, state.disk_write, 0, 0))
                self.db.conn.commit()
                self._enforce_limits(app_id, state)
            except (psutil.NoSuchProcess, ProcessLookupError):
                state.status = "stopped"

    def _should_restart(self, policy: str | None, code: int | None, state) -> bool:
        policy = policy or self.manager.defaults.restart_policy
        max_retries = state.config.restart_max_retries or self.manager.defaults.restart_max_retries
        if state.restart_count >= max_retries:
            return False
        return policy == "always" or (policy == "on_failure" and code not in (0, None))

    def _enforce_limits(self, app_id: str, state) -> None:
        cpu_limit = state.config.cpu_limit or self.manager.defaults.cpu_limit
        cpu_duration = state.config.cpu_duration or self.manager.defaults.cpu_duration
        ram_limit = state.config.ram_limit or self.manager.defaults.ram_limit
        now = time.time()
        if state.cpu > cpu_limit:
            self.cpu_over_since[app_id] = self.cpu_over_since[app_id] or now
            if now - self.cpu_over_since[app_id] >= cpu_duration:
                self.db.event("error", f"CPU limit exceeded by {state.config.name}", app_id, cpu=state.cpu)
                self.manager.stop(app_id, kill=True)
                if self._should_restart(state.config.restart_policy, 1, state):
                    self.manager.restart(app_id, "cpu_limit")
        else:
            self.cpu_over_since[app_id] = 0
        if state.ram > ram_limit:
            self.db.event("error", f"RAM limit exceeded by {state.config.name}", app_id, ram=state.ram)
            self.manager.stop(app_id, kill=True)
            if self._should_restart(state.config.restart_policy, 1, state):
                self.manager.restart(app_id, "ram_limit")

    async def stop(self) -> None:
        self.running = False
