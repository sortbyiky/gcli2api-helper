import asyncio
import json
import logging
import secrets
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import config
from services.api_client import GcliApiClient
from services.auto_verify import auto_verify_service
from services.log_forwarder import log_forwarder
from services.quota_monitor import quota_monitor_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_client: Optional[GcliApiClient] = None

# Session token for login
_session_token: Optional[str] = None

# SSE clients management
sse_clients: List[asyncio.Queue] = []

# Cache for git version info (populated at startup)
_git_version_cache: Optional[Dict[str, str]] = None


def get_git_version() -> Dict[str, str]:
    """Get version info from git, with fallback to version.txt"""
    global _git_version_cache

    if _git_version_cache is not None:
        return _git_version_cache

    project_root = Path(__file__).parent

    # Try to get version from git
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h|%H|%s|%ci"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|", 3)
            if len(parts) == 4:
                _git_version_cache = {
                    "short_hash": parts[0],
                    "full_hash": parts[1],
                    "message": parts[2],
                    "date": parts[3],
                }
                logger.info(f"Version from git: {_git_version_cache['short_hash']}")
                return _git_version_cache
    except Exception as e:
        logger.debug(f"Failed to get version from git: {e}")

    # Fallback to version.txt
    version_file = project_root / "version.txt"
    if version_file.exists():
        version_data = {}
        with open(version_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    version_data[key] = value
        if version_data:
            _git_version_cache = version_data
            logger.info(f"Version from file: {version_data.get('short_hash', 'unknown')}")
            return _git_version_cache

    _git_version_cache = {"short_hash": "unknown", "full_hash": "", "message": "", "date": ""}
    return _git_version_cache


async def broadcast_log(log_entry: dict):
    """Broadcast new log to all SSE clients"""
    for queue in sse_clients:
        try:
            await queue.put(log_entry)
        except Exception:
            pass


# Set SSE callback for auto_verify_service and log_forwarder
auto_verify_service.set_log_callback(broadcast_log)
log_forwarder.set_log_callback(broadcast_log)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("gcli2api-helper starting...")
    # Try to connect if auto_connect is enabled and config exists
    if config.auto_connect and config.gcli_url and config.gcli_password:
        try:
            await connect_to_gcli()
            logger.info("Auto-connected to gcli2api on startup")
        except Exception as e:
            logger.warning(f"Failed to auto-connect on startup: {e}")
    yield
    # Cleanup
    logger.info("gcli2api-helper shutting down...")
    await auto_verify_service.stop()
    await log_forwarder.disconnect()
    if api_client:
        await api_client.close()


app = FastAPI(title="gcli2api-helper", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"


# --- Models ---

class ConnectRequest(BaseModel):
    url: str
    password: str


class ConfigRequest(BaseModel):
    gcli_url: Optional[str] = None
    gcli_password: Optional[str] = None
    auto_verify_enabled: Optional[bool] = None
    auto_verify_interval: Optional[int] = None
    auto_verify_error_codes: Optional[List[int]] = None
    quota_refresh_interval: Optional[int] = None


# --- Helper Functions ---

async def connect_to_gcli():
    global api_client
    if api_client:
        await api_client.close()
    api_client = GcliApiClient(config.gcli_url)
    await api_client.login(config.gcli_password)
    auto_verify_service.set_client(api_client)
    quota_monitor_service.set_client(api_client)
    quota_monitor_service.set_cache_ttl(config.quota_refresh_interval)
    logger.info(f"Connected to {config.gcli_url}")

    # Start log forwarder to receive gcli2api logs
    await log_forwarder.disconnect()  # Disconnect if already connected
    await log_forwarder.connect(config.gcli_url, config.gcli_password)

    # Start auto verify if enabled
    if config.auto_verify_enabled:
        await auto_verify_service.start(
            config.auto_verify_interval,
            config.auto_verify_error_codes
        )


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>gcli2api-helper</h1><p>Static files not found</p>")


@app.post("/api/connect")
async def api_connect(req: ConnectRequest):
    config.gcli_url = req.url
    config.gcli_password = req.password
    config.save()
    try:
        await connect_to_gcli()
        return {"success": True, "message": "Connected"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/login")
async def api_login(req: ConnectRequest):
    """Login and establish connection, return session token"""
    global _session_token
    config.gcli_url = req.url
    config.gcli_password = req.password
    config.save()
    try:
        await connect_to_gcli()
        _session_token = secrets.token_hex(32)
        logger.info(f"User logged in, session created")
        return {"success": True, "token": _session_token}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/session")
async def api_check_session(token: str = ""):
    """Check if session token is valid"""
    if _session_token and token == _session_token:
        return {"success": True, "valid": True, "connected": api_client is not None}
    return {"success": True, "valid": False}


@app.post("/api/logout")
async def api_logout():
    """Logout and clear session"""
    global _session_token
    _session_token = None
    logger.info("User logged out")
    return {"success": True}


@app.get("/api/config")
async def api_get_config():
    return {
        "success": True,
        "config": config.to_dict(),
        "connected": api_client is not None,
    }


@app.post("/api/config")
async def api_save_config(req: ConfigRequest):
    if req.gcli_url is not None:
        config.gcli_url = req.gcli_url
    if req.gcli_password is not None:
        config.gcli_password = req.gcli_password
    if req.auto_verify_enabled is not None:
        config.auto_verify_enabled = req.auto_verify_enabled
    if req.auto_verify_interval is not None:
        config.auto_verify_interval = max(60, req.auto_verify_interval)
    if req.auto_verify_error_codes is not None:
        config.auto_verify_error_codes = req.auto_verify_error_codes
    if req.quota_refresh_interval is not None:
        config.quota_refresh_interval = max(60, req.quota_refresh_interval)
        quota_monitor_service.set_cache_ttl(config.quota_refresh_interval)
    config.save()

    # Restart auto verify if needed
    if api_client:
        if config.auto_verify_enabled:
            await auto_verify_service.stop()
            await auto_verify_service.start(
                config.auto_verify_interval,
                config.auto_verify_error_codes
            )
        else:
            await auto_verify_service.stop()

    return {"success": True, "config": config.to_dict()}


@app.get("/api/verify/status")
async def api_verify_status():
    return {
        "success": True,
        "enabled": config.auto_verify_enabled,
        "running": auto_verify_service.is_running,
        "interval": config.auto_verify_interval,
        "error_codes": config.auto_verify_error_codes,
        "status": auto_verify_service.get_status(),
    }


@app.get("/api/verify/history")
async def api_verify_history():
    return {
        "success": True,
        "history": auto_verify_service.history,
    }


@app.get("/api/verify/logs/stream")
async def api_logs_stream(request: Request):
    """SSE endpoint for real-time log streaming"""
    queue = asyncio.Queue()
    sse_clients.append(queue)

    async def event_generator():
        try:
            # Send initial history on connect
            yield {
                "event": "init",
                "data": json.dumps(auto_verify_service.history)
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": "log",
                        "data": json.dumps(data)
                    }
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield {"event": "heartbeat", "data": ""}
        finally:
            if queue in sse_clients:
                sse_clients.remove(queue)

    return EventSourceResponse(event_generator())


@app.post("/api/verify/trigger")
async def api_verify_trigger():
    if not api_client:
        raise HTTPException(status_code=400, detail="Not connected")
    result = await auto_verify_service.trigger_now(config.auto_verify_error_codes)
    return result


@app.get("/api/verify/history/download")
async def api_verify_history_download():
    """Download verify history as text file"""
    content = auto_verify_service.export_history()
    if not content:
        content = "No history records"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gcli2api-helper_logs_{timestamp}.txt"
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/verify/history/clear")
async def api_verify_history_clear():
    """Clear verify history"""
    auto_verify_service.clear_history()
    return {"success": True, "message": "History cleared"}


@app.get("/api/quota")
async def api_get_quota(refresh: bool = False):
    if not api_client:
        raise HTTPException(status_code=400, detail="Not connected")
    result = await quota_monitor_service.get_all_quotas(force_refresh=refresh)
    return result


@app.post("/api/quota/refresh")
async def api_refresh_quota():
    if not api_client:
        raise HTTPException(status_code=400, detail="Not connected")
    result = await quota_monitor_service.get_all_quotas(force_refresh=True)
    return result


@app.get("/api/quota/paginated")
async def api_get_quota_paginated(page: int = 1, page_size: int = 9, refresh: bool = False):
    """Get quotas with backend pagination"""
    if not api_client:
        raise HTTPException(status_code=400, detail="Not connected")
    result = await quota_monitor_service.get_quotas_paginated(
        page=page,
        page_size=page_size,
        force_refresh=refresh
    )
    return result


@app.get("/api/status")
async def api_status():
    return {
        "success": True,
        "connected": api_client is not None,
        "gcli_url": config.gcli_url,
        "auto_verify": auto_verify_service.get_status(),
        "quota_monitor": quota_monitor_service.get_status(),
        "log_forwarder": log_forwarder.get_status(),
    }


@app.get("/api/stats")
async def api_get_stats():
    """获取模型调用统计数据"""
    return {
        "success": True,
        "stats": log_forwarder.get_stats(),
    }


@app.post("/api/stats/reset")
async def api_reset_stats():
    """重置统计数据"""
    log_forwarder.reset_stats()
    return {"success": True, "message": "Stats reset"}


@app.get("/api/version")
async def api_version(check_update: bool = False):
    """Get version info and optionally check for updates"""
    import httpx

    # Get version from git (or fallback to version.txt)
    version_data = get_git_version()

    if not version_data.get("short_hash"):
        return {"success": False, "error": "Cannot get version info"}

    response_data = {
        "success": True,
        "version": version_data.get("short_hash", "unknown"),
        "full_hash": version_data.get("full_hash", ""),
        "message": version_data.get("message", ""),
        "date": version_data.get("date", ""),
    }

    if check_update:
        try:
            github_url = "https://raw.githubusercontent.com/sortbyiky/gcli2api-helper/main/version.txt"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(github_url)
                if resp.status_code == 200:
                    remote_data = {}
                    for line in resp.text.strip().split("\n"):
                        line = line.strip()
                        if "=" in line:
                            key, value = line.split("=", 1)
                            remote_data[key] = value

                    latest_hash = remote_data.get("full_hash", "")
                    current_hash = version_data.get("full_hash", "")
                    has_update = (current_hash != latest_hash) if current_hash and latest_hash else None

                    response_data["check_update"] = True
                    response_data["has_update"] = has_update
                    response_data["latest_version"] = remote_data.get("short_hash", "")
                    response_data["latest_hash"] = latest_hash
                    response_data["latest_message"] = remote_data.get("message", "")
                    response_data["latest_date"] = remote_data.get("date", "")
                else:
                    response_data["check_update"] = False
                    response_data["update_error"] = f"GitHub returned {resp.status_code}"
        except Exception as e:
            logger.debug(f"Check update failed: {e}")
            response_data["check_update"] = False
            response_data["update_error"] = str(e)

    return response_data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7862)
