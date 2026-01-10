import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .api_client import GcliApiClient

logger = logging.getLogger(__name__)


class AutoVerifyService:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[GcliApiClient] = None
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100
        self._on_new_log = None  # SSE callback

    def set_log_callback(self, callback):
        """Set callback for new log entries (for SSE)"""
        self._on_new_log = callback

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def history(self) -> List[Dict[str, Any]]:
        return self._history

    def set_client(self, client: GcliApiClient):
        self._client = client

    async def start(self, interval: int, error_codes: List[int]):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval, error_codes))
        logger.info(f"Auto verify started, interval={interval}s, error_codes={error_codes}")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Auto verify stopped")

    async def _run_loop(self, interval: int, error_codes: List[int]):
        while self._running:
            try:
                await self._add_history({
                    "type": "info",
                    "message": f"开始定时检验，检查错误码: {error_codes}"
                })
                await self._check_and_verify(error_codes)
            except Exception as e:
                logger.error(f"Auto verify error: {e}")
                await self._add_history({"type": "error", "message": str(e)})
            await asyncio.sleep(interval)

    async def _check_and_verify(self, error_codes: List[int]):
        if not self._client:
            await self._add_history({"type": "warning", "message": "未连接到 gcli2api"})
            return

        # Get disabled credentials
        disabled = await self._client.get_disabled_credentials()
        if not disabled:
            await self._add_history({"type": "info", "message": "检验完成，没有发现禁用的凭证"})
            return

        # Filter by error codes
        to_verify = []
        for cred in disabled:
            cred_errors = cred.get("error_codes", [])
            if any(code in error_codes for code in cred_errors):
                to_verify.append(cred)

        if not to_verify:
            await self._add_history({
                "type": "info",
                "message": f"检验完成，{len(disabled)} 个禁用凭证，但无匹配错误码 {error_codes}"
            })
            return

        logger.info(f"Found {len(to_verify)} credentials to verify")

        # Verify each credential
        for cred in to_verify:
            filename = cred.get("filename")
            if not filename:
                continue
            try:
                result = await self._client.verify_credential(filename)
                success = result.get("success", False)
                await self._add_history({
                    "type": "verify",
                    "filename": filename,
                    "success": success,
                    "message": result.get("message", ""),
                })
                logger.info(f"Verified {filename}: success={success}")
            except Exception as e:
                await self._add_history({
                    "type": "verify",
                    "filename": filename,
                    "success": False,
                    "message": str(e),
                })
                logger.warning(f"Failed to verify {filename}: {e}")

    async def trigger_now(self, error_codes: List[int] = None) -> Dict[str, Any]:
        """Manually trigger verification for all credentials"""
        if not self._client:
            return {"success": False, "message": "Not connected"}

        results = []
        # Get all credentials (not just disabled)
        all_creds = await self._client.get_all_credentials()

        for cred in all_creds:
            filename = cred.get("filename")
            if not filename:
                continue
            try:
                result = await self._client.verify_credential(filename)
                results.append({
                    "filename": filename,
                    "success": result.get("success", False),
                    "message": result.get("message", ""),
                })
                await self._add_history({
                    "type": "verify",
                    "filename": filename,
                    "success": result.get("success", False),
                    "message": result.get("message", ""),
                })
            except Exception as e:
                results.append({
                    "filename": filename,
                    "success": False,
                    "message": str(e),
                })

        return {
            "success": True,
            "total": len(all_creds),
            "verified": len(results),
            "results": results,
        }

    async def _add_history(self, entry: Dict[str, Any]):
        entry["timestamp"] = datetime.now().isoformat()
        self._history.insert(0, entry)
        if len(self._history) > self._max_history:
            self._history = self._history[:self._max_history]
        # Trigger SSE callback
        if self._on_new_log:
            await self._on_new_log(entry)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "history_count": len(self._history),
        }

    def clear_history(self):
        """Clear all history records"""
        self._history = []

    def export_history(self) -> str:
        """Export history as text format"""
        lines = []
        for entry in self._history:
            timestamp = entry.get("timestamp", "")
            entry_type = entry.get("type", "unknown")
            filename = entry.get("filename", "")
            success = entry.get("success", False)
            message = entry.get("message", "")

            if entry_type == "verify":
                status = "SUCCESS" if success else "FAILED"
                lines.append(f"[{timestamp}] [{status}] {filename} - {message}")
            elif entry_type == "error":
                lines.append(f"[{timestamp}] [ERROR] {message}")
            else:
                lines.append(f"[{timestamp}] [{entry_type.upper()}] {message}")

        return "\n".join(lines)


auto_verify_service = AutoVerifyService()
