import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import config
from services.api_client import GcliApiClient
from services.auto_verify import auto_verify_service
from services.quota_monitor import quota_monitor_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_client: Optional[GcliApiClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("gcli2api-helper starting...")
    # Try to connect if config exists
    if config.gcli_url and config.gcli_password:
        try:
            await connect_to_gcli()
        except Exception as e:
            logger.warning(f"Failed to connect on startup: {e}")
    yield
    # Cleanup
    logger.info("gcli2api-helper shutting down...")
    await auto_verify_service.stop()
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


@app.get("/api/status")
async def api_status():
    return {
        "success": True,
        "connected": api_client is not None,
        "gcli_url": config.gcli_url,
        "auto_verify": auto_verify_service.get_status(),
        "quota_monitor": quota_monitor_service.get_status(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7862)
