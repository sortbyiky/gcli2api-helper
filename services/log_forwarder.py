import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed
from .model_stats import ModelStatsService

logger = logging.getLogger(__name__)


class LogForwarder:
    """Connect to gcli2api WebSocket and forward logs to helper SSE"""

    def __init__(self):
        self._ws = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_log: Optional[Callable] = None
        self._base_url: Optional[str] = None
        self._token: Optional[str] = None
        self._reconnect_delay = 5  # seconds
        self._stats = ModelStatsService()  # 统计服务

    def set_log_callback(self, callback: Callable):
        """Set callback for new log entries (for SSE)"""
        self._on_log = callback

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws is not None

    async def connect(self, base_url: str, token: str):
        """Connect to gcli2api WebSocket /auth/logs/stream"""
        self._base_url = base_url
        self._token = token
        self._running = True
        self._task = asyncio.create_task(self._connect_loop())
        logger.info(f"LogForwarder started, connecting to {base_url}")

    async def disconnect(self):
        """Disconnect from gcli2api WebSocket"""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("LogForwarder disconnected")

    async def _connect_loop(self):
        """Reconnect loop for WebSocket connection"""
        while self._running:
            try:
                await self._connect_and_forward()
            except Exception as e:
                logger.warning(f"LogForwarder connection error: {e}")
                if self._on_log:
                    await self._on_log({
                        "type": "warning",
                        "message": f"gcli2api 日志连接断开: {e}",
                        "source": "helper",
                    })
            if self._running:
                logger.info(f"LogForwarder reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_and_forward(self):
        """Connect to WebSocket and forward logs"""
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/auth/logs/stream"

        logger.info(f"Connecting to WebSocket: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            self._ws = ws
            logger.info("LogForwarder connected to gcli2api")

            if self._on_log:
                await self._on_log({
                    "type": "info",
                    "message": "已连接到 gcli2api 日志流",
                    "source": "helper",
                })

            while self._running:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    if message and self._on_log:
                        # 解析日志进行统计
                        self._stats.parse_log(message.strip())

                        await self._on_log({
                            "type": "gcli2api",
                            "message": message.strip(),
                            "source": "gcli2api",
                            "timestamp": datetime.now().isoformat(),
                        })
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    try:
                        await ws.ping()
                    except Exception:
                        break
                except ConnectionClosed:
                    logger.info("WebSocket connection closed")
                    break

        self._ws = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "base_url": self._base_url,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        return self._stats.get_stats()

    def reset_stats(self):
        """重置统计数据"""
        self._stats.reset()


log_forwarder = LogForwarder()
