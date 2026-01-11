import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .api_client import GcliApiClient

logger = logging.getLogger(__name__)


class QuotaMonitorService:
    def __init__(self):
        self._client: Optional[GcliApiClient] = None
        self._cache: List[Dict[str, Any]] = []
        self._cache_time: Optional[datetime] = None
        self._cache_ttl: int = 300  # 5 minutes
        self._refreshing = False

    def set_client(self, client: GcliApiClient):
        self._client = client

    def set_cache_ttl(self, ttl: int):
        self._cache_ttl = ttl

    @property
    def is_cache_valid(self) -> bool:
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl

    async def get_all_quotas(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not self._client:
            return {"success": False, "message": "Not connected", "data": []}

        if not force_refresh and self.is_cache_valid:
            return {
                "success": True,
                "data": self._cache,
                "cached": True,
                "cache_time": self._cache_time.isoformat() if self._cache_time else None,
            }

        if self._refreshing:
            return {
                "success": True,
                "data": self._cache,
                "cached": True,
                "refreshing": True,
                "cache_time": self._cache_time.isoformat() if self._cache_time else None,
            }

        try:
            self._refreshing = True
            quotas = await self._client.get_all_quotas()
            self._cache = quotas
            self._cache_time = datetime.now()
            return {
                "success": True,
                "data": quotas,
                "cached": False,
                "cache_time": self._cache_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get quotas: {e}")
            return {
                "success": False,
                "message": str(e),
                "data": self._cache,
                "cached": True,
            }
        finally:
            self._refreshing = False

    async def get_quotas_paginated(
        self, page: int = 1, page_size: int = 9, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get quotas with pagination - fetches only the requested page"""
        if not self._client:
            return {"success": False, "message": "Not connected", "data": [], "total": 0}

        try:
            result = await self._client.get_quotas_paginated(page=page, page_size=page_size)
            return {
                "success": True,
                "data": result["items"],
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": result["total_pages"],
                "cached": False,
                "cache_time": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get paginated quotas: {e}")
            return {
                "success": False,
                "message": str(e),
                "data": [],
                "total": 0,
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "cache_valid": self.is_cache_valid,
            "cache_count": len(self._cache),
            "cache_time": self._cache_time.isoformat() if self._cache_time else None,
            "cache_ttl": self._cache_ttl,
            "refreshing": self._refreshing,
        }


quota_monitor_service = QuotaMonitorService()
