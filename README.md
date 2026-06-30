# PythonEngine

PythonEngine is a lightweight production-oriented process manager for running many Python applications inside one Docker container or Linux host. It provides sequential startup from `startup.txt`, per-app subprocess isolation, file-based logs with rotation, SQLite persistence, psutil resource monitoring, restart policies, resource limits, a FastAPI REST API, WebSocket live logs, Prometheus metrics, and a modern Tailwind/Chart.js dashboard.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python engine.py
```

Open <http://localhost:8080>. Default credentials are `admin` / `admin`; change the password hash and session secrets in `config.yaml` before production.

## Startup file

`startup.txt` contains one Python file per line. Blank lines and lines beginning with `#` are ignored. Applications start sequentially in file order; each process is checked before the configurable delay is applied and the next app is started.

## Configuration

Edit `config.yaml` to configure engine host/port, database location, monitoring interval, log rotation, authentication, WebSocket limits, defaults, and app-specific overrides. Per-app settings include path, arguments, working directory, environment variables, CPU/RAM limits, restart policy, health check URL, tags, favorites, grouping, and scheduled restart metadata.

## REST API

Authenticated endpoints include:

- `GET /api/apps`
- `GET /api/app/{id}`
- `POST /api/app/{id}/start|stop|restart|kill|delete`
- `GET /api/logs/{id}`
- `POST /api/logs/{id}/clear`
- `GET /api/events`
- `GET /api/system`
- `GET /api/config`
- `POST /api/config`
- `GET /metrics` for Prometheus-compatible metrics

State-changing API requests require the `x-csrf-token` header from the dashboard session.

## Docker

```bash
docker compose up --build
```

Persistent volumes are mapped for `apps`, `logs`, and `data`. The image runs `python engine.py` and exposes port `8080`.

## Operations guide

- Logs are streamed from disk; the engine does not buffer full application logs in memory.
- Use `/api/logs/{id}?download=true` to download logs.
- Resource history, events, crash records, restart records, configuration, and audit logs are stored in SQLite.
- Graceful shutdown terminates child processes, waits, and force-kills remaining children.
- Paths are validated to stay within the project and subprocesses are launched without `shell=True`.

## Troubleshooting

- If an app fails to start, verify the path exists, ends in `.py`, and is inside the project directory.
- If login fails, regenerate the bcrypt password hash with Passlib and update `config.yaml`.
- If the dashboard cannot load CDN assets, vendor Tailwind and Chart.js into `pythonengine/web/static` for fully offline environments.

## Development

The project is split into configuration, process management, monitoring, logging, database, authentication, web/API, templates, and static assets. Python 3.12+, type hints, docstrings, and simple modular services are used throughout.
