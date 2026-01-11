import httpx
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class GcliApiClient:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    def _headers(self) -> Dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def login(self, password: str) -> Dict[str, Any]:
        """Login and get token (password is token in gcli2api)"""
        url = f"{self.base_url}/auth/login"
        resp = await self.client.post(url, json={"password": password})
        resp.raise_for_status()
        data = resp.json()
        self.token = data.get("token", password)
        return data

    async def get_credentials(
        self,
        status_filter: str = "all",
        error_code_filter: str = "all",
        mode: str = "antigravity",
        offset: int = 0,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Get credentials list with filters"""
        url = f"{self.base_url}/creds/status"
        params = {
            "token": self.token,
            "status_filter": status_filter,
            "error_code_filter": error_code_filter,
            "mode": mode,
            "offset": offset,
            "limit": limit,
        }
        resp = await self.client.get(url, params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def get_disabled_credentials(self, mode: str = "antigravity") -> List[Dict[str, Any]]:
        """Get only disabled credentials"""
        result = await self.get_credentials(status_filter="disabled", mode=mode)
        return result.get("items", [])

    async def get_all_credentials(self, mode: str = "antigravity") -> List[Dict[str, Any]]:
        """Get all credentials (no status filter)"""
        result = await self.get_credentials(status_filter="all", mode=mode)
        return result.get("items", [])

    async def verify_credential(self, filename: str, mode: str = "antigravity") -> Dict[str, Any]:
        """Verify a single credential"""
        url = f"{self.base_url}/creds/verify-project/{filename}"
        params = {"token": self.token, "mode": mode}
        resp = await self.client.post(url, params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def get_credential_quota(self, filename: str) -> Dict[str, Any]:
        """Get quota for a credential (antigravity mode only)"""
        url = f"{self.base_url}/creds/quota/{filename}"
        params = {"token": self.token, "mode": "antigravity"}
        resp = await self.client.get(url, params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def get_all_quotas(self) -> List[Dict[str, Any]]:
        """Get quotas for all credentials"""
        creds = await self.get_credentials(mode="antigravity")
        items = creds.get("items", [])
        results = []
        for item in items:
            filename = item.get("filename")
            if not filename:
                continue
            try:
                quota = await self.get_credential_quota(filename)
                results.append({
                    "filename": filename,
                    "user_email": item.get("user_email", ""),
                    "disabled": item.get("disabled", False),
                    "quota": quota,
                })
            except Exception as e:
                logger.warning(f"Failed to get quota for {filename}: {e}")
                results.append({
                    "filename": filename,
                    "user_email": item.get("user_email", ""),
                    "disabled": item.get("disabled", False),
                    "quota": {"success": False, "error": str(e)},
                })
        return results

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to gcli2api"""
        url = f"{self.base_url}/version/info"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()
