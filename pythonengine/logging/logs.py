"""File-based application logging and rotation."""
from __future__ import annotations

import shutil
from pathlib import Path

from pythonengine.config.models import LoggingConfig


class LogService:
    def __init__(self, config: LoggingConfig) -> None:
        self.config = config
        self.dir = Path(config.directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.engine_log = self.dir / "engine.log"

    def app_log(self, app_id: str) -> Path:
        safe = "".join(c for c in app_id if c.isalnum() or c in "-_.")
        return self.dir / f"{safe}.log"

    def rotate(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size < self.config.max_bytes:
            return
        for idx in range(self.config.backups - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{idx}")
            dst = path.with_suffix(path.suffix + f".{idx + 1}")
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
        shutil.move(path, path.with_suffix(path.suffix + ".1"))
        path.touch()

    def clear(self, app_id: str) -> None:
        self.app_log(app_id).write_text("", encoding="utf-8")
