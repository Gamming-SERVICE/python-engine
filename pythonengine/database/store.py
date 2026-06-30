"""SQLite persistence for PythonEngine."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, level TEXT, message TEXT, data TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS resource_history (id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, cpu REAL, ram INTEGER, threads INTEGER, files INTEGER, disk_read INTEGER, disk_write INTEGER, net_sent INTEGER, net_recv INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS restarts (id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, reason TEXT, count INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS crashes (id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, exit_code INTEGER, message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, data TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS configuration (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def event(self, level: str, message: str, app_id: str | None = None, **data: Any) -> None:
        with self.tx() as db:
            db.execute("INSERT INTO events(app_id, level, message, data) VALUES(?,?,?,?)",
                       (app_id, level, message, json.dumps(data)))

    def audit(self, actor: str, action: str, target: str, **data: Any) -> None:
        with self.tx() as db:
            db.execute("INSERT INTO audit_log(actor, action, target, data) VALUES(?,?,?,?)",
                       (actor, action, target, json.dumps(data)))

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def close(self) -> None:
        self.conn.close()
