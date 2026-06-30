"""FastAPI web/API/WebSocket application."""
from __future__ import annotations

import asyncio
from pathlib import Path

import psutil
import yaml
from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from pythonengine.auth.security import csrf_token, require_login, verify_csrf, verify_password
from pythonengine.config.loader import load_config
from pythonengine.core.process import ProcessManager
from pythonengine.database.store import Database
from pythonengine.logging.logs import LogService
from pythonengine.monitoring.service import MonitorService

BASE = Path(__file__).parent

def create_app() -> FastAPI:
    config = load_config()
    db = Database(config.engine.database_location)
    logs = LogService(config.logging)
    manager = ProcessManager(config.apps, config.defaults, logs, db)
    monitor = MonitorService(manager, db, config.engine.monitoring_interval)
    app = FastAPI(title="PythonEngine", version="1.0.0")
    app.add_middleware(SessionMiddleware, secret_key=config.security.session_secret, same_site="lax", https_only=False)
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")
    app.state.config, app.state.db, app.state.manager, app.state.monitor, app.state.logs = config, db, manager, monitor, logs

    @app.on_event("startup")
    async def startup() -> None:
        db.event("info", "PythonEngine started")
        asyncio.create_task(monitor.run())
        for state in manager.apps.values():
            if state.config.enabled and state.config.auto_start:
                try:
                    await asyncio.to_thread(manager.start, state.config.id)
                except Exception as exc:
                    state.status = "failed"; state.last_error = str(exc)
                    db.event("error", f"Startup failed: {exc}", state.config.id)
                await asyncio.sleep(state.config.startup_delay or config.engine.startup_delay)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await monitor.stop()
        for app_id in list(manager.apps):
            try: manager.stop(app_id)
            except Exception: pass
        db.event("info", "PythonEngine stopped")
        db.close()

    def auth_dep(request: Request) -> None: require_login(request)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request, "csrf": csrf_token(request)})

    @app.post("/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...), csrf: str = Form(...)):
        verify_csrf(request, csrf)
        if username == config.authentication.username and verify_password(password, config.authentication.password_hash):
            request.session["user"] = username; db.audit(username, "login", "dashboard")
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse("login.html", {"request": request, "csrf": csrf_token(request), "error": "Invalid credentials"}, status_code=401)

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear(); return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth_dep)])
    async def home(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request, "csrf": csrf_token(request)})

    @app.get("/apps/{app_id}", response_class=HTMLResponse, dependencies=[Depends(auth_dep)])
    async def app_detail(request: Request, app_id: str):
        return templates.TemplateResponse("app.html", {"request": request, "app": manager.get(app_id).to_dict(), "csrf": csrf_token(request)})

    @app.get("/api/apps", dependencies=[Depends(auth_dep)])
    async def api_apps(): return manager.snapshot()

    @app.get("/api/app/{app_id}", dependencies=[Depends(auth_dep)])
    async def api_app(app_id: str): return manager.get(app_id).to_dict()

    @app.post("/api/app/{app_id}/{action}", dependencies=[Depends(auth_dep)])
    async def app_action(request: Request, app_id: str, action: str):
        token = request.headers.get("x-csrf-token")
        verify_csrf(request, token)
        if action == "start": result = manager.start(app_id)
        elif action == "stop": result = manager.stop(app_id)
        elif action == "restart": result = manager.restart(app_id)
        elif action == "kill": result = manager.stop(app_id, True)
        elif action == "delete": result = manager.stop(app_id); manager.apps.pop(app_id, None)
        else: raise HTTPException(404, "unknown action")
        db.audit(request.session.get("user", "api"), action, app_id)
        return result.to_dict()

    @app.get("/api/logs/{app_id}", dependencies=[Depends(auth_dep)])
    async def api_logs(app_id: str, download: bool = False, tail: int = 500):
        path = logs.app_log(app_id)
        if download: return FileResponse(path, filename=path.name)
        if not path.exists(): return PlainTextResponse("")
        lines = path.read_text(errors="replace").splitlines()[-tail:]
        return PlainTextResponse("\n".join(lines))

    @app.post("/api/logs/{app_id}/clear", dependencies=[Depends(auth_dep)])
    async def clear_logs(request: Request, app_id: str):
        verify_csrf(request, request.headers.get("x-csrf-token")); logs.clear(app_id); return {"ok": True}

    @app.get("/api/events", dependencies=[Depends(auth_dep)])
    async def events(): return db.rows("SELECT * FROM events ORDER BY id DESC LIMIT 100")

    @app.get("/api/system", dependencies=[Depends(auth_dep)])
    async def system():
        return {"cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory()._asdict(), "disk": psutil.disk_usage('.')._asdict(), "boot_time": psutil.boot_time(), "apps": manager.snapshot()}

    @app.get("/api/config", dependencies=[Depends(auth_dep)])
    async def get_config(): return config.raw

    @app.post("/api/config", dependencies=[Depends(auth_dep)])
    async def set_config(request: Request):
        verify_csrf(request, request.headers.get("x-csrf-token")); data = await request.json()
        Path("config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8"); db.audit(request.session.get("user", "api"), "config_update", "engine"); return {"ok": True}

    @app.get("/metrics")
    async def metrics():
        lines = ["# TYPE pythonengine_app_cpu gauge"]
        for s in manager.apps.values():
            lines.append(f'pythonengine_app_cpu{{app="{s.config.id}"}} {s.cpu}')
            lines.append(f'pythonengine_app_ram_bytes{{app="{s.config.id}"}} {s.ram}')
        return PlainTextResponse("\n".join(lines))

    @app.websocket("/ws/{channel}/{app_id}")
    async def ws(websocket: WebSocket, channel: str, app_id: str):
        await websocket.accept(); pos = 0
        try:
            while True:
                if channel == "logs":
                    p = logs.app_log(app_id); p.touch(exist_ok=True)
                    with p.open("r", errors="replace") as f:
                        f.seek(pos); chunk = f.read(); pos = f.tell()
                    if chunk: await websocket.send_text(chunk)
                else:
                    await websocket.send_json({"apps": manager.snapshot()})
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            return
    return app
