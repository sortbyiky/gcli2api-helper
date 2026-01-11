import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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
        self._on_progress = None  # Progress callback for SSE

    def set_log_callback(self, callback):
        """Set callback for new log entries (for SSE)"""
        self._on_new_log = callback

    def set_progress_callback(self, callback: Optional[Callable]):
        """Set callback for verify progress (for SSE)"""
        self._on_progress = callback

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

        # Get all credentials (not just disabled)
        all_creds = await self._client.get_all_credentials()
        if not all_creds:
            await self._add_history({"type": "info", "message": "检验完成，没有发现凭证"})
            return

        # Filter by error codes - check all credentials with matching error codes
        to_verify = []
        for cred in all_creds:
            cred_errors = cred.get("error_codes", [])
            if any(code in error_codes for code in cred_errors):
                to_verify.append(cred)

        if not to_verify:
            await self._add_history({
                "type": "info",
                "message": f"检验完成，{len(all_creds)} 个凭证，无匹配错误码 {error_codes}"
            })
            return

        logger.info(f"Found {len(to_verify)} credentials to verify")
        await self._add_history({
            "type": "info",
            "message": f"发现 {len(to_verify)} 个需要恢复的凭证，开始并行检验..."
        })

        # Use parallel verification with progress callback
        async def progress_callback(completed: int, total: int, filename: str, success: bool):
            if self._on_progress:
                await self._on_progress(completed, total, filename, success)

        results = await self._client.verify_credentials_batch(
            to_verify,
            progress_callback=progress_callback
        )

        # Process results and add to history
        success_count = 0
        fail_count = 0
        for item in results:
            filename = item.get("filename", "")
            success = item.get("success", False)
            result = item.get("result", {})
            message = result.get("message", "")

            if success:
                success_count += 1
                await self._add_history({
                    "type": "verify",
                    "filename": filename,
                    "success": True,
                    "message": f"恢复成功 - {message}" if message else "恢复成功，凭证已启用",
                })
            else:
                fail_count += 1
                error_msg = result.get("error", message)
                await self._add_history({
                    "type": "verify",
                    "filename": filename,
                    "success": False,
                    "message": f"恢复失败 - {error_msg}" if error_msg else "恢复失败",
                })

        # Summary log
        await self._add_history({
            "type": "info",
            "message": f"本轮检验完成: 成功 {success_count} 个, 失败 {fail_count} 个"
        })

    async def trigger_now(self, error_codes: List[int] = None) -> Dict[str, Any]:
        """Manually trigger verification for all credentials (parallel execution)"""
        if not self._client:
            return {"success": False, "message": "Not connected"}

        # Get all credentials (not just disabled)
        all_creds = await self._client.get_all_credentials()
        if not all_creds:
            return {"success": True, "total": 0, "verified": 0, "results": []}

        await self._add_history({
            "type": "info",
            "message": f"开始立即检验，共 {len(all_creds)} 个凭证，并行执行中..."
        })

        # Use parallel verification with progress callback
        async def progress_callback(completed: int, total: int, filename: str, success: bool):
            if self._on_progress:
                await self._on_progress(completed, total, filename, success)

        batch_results = await self._client.verify_credentials_batch(
            all_creds,
            progress_callback=progress_callback
        )

        # Process results and add to history
        results = []
        success_count = 0
        fail_count = 0
        for item in batch_results:
            filename = item.get("filename", "")
            success = item.get("success", False)
            result = item.get("result", {})
            message = result.get("message", "")

            results.append({
                "filename": filename,
                "success": success,
                "message": message,
            })

            if success:
                success_count += 1
            else:
                fail_count += 1

            await self._add_history({
                "type": "verify",
                "filename": filename,
                "success": success,
                "message": message if message else ("检验成功" if success else "检验失败"),
            })

        await self._add_history({
            "type": "info",
            "message": f"立即检验完成: 成功 {success_count} 个, 失败 {fail_count} 个"
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
