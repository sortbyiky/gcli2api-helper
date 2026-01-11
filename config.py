import json
import os
from pathlib import Path
from typing import List, Optional

CONFIG_FILE = Path(__file__).parent / "config.json"

class Config:
    def __init__(self):
        self.gcli_url: str = "http://127.0.0.1:7861"
        self.gcli_password: str = ""
        self.auto_connect: bool = True  # Auto connect on startup
        self.auto_verify_enabled: bool = False
        self.auto_verify_interval: int = 300  # seconds
        self.auto_verify_error_codes: List[int] = [403]  # Only 403 (permission issues), not 400 (client errors)
        self.quota_refresh_interval: int = 300  # 5 minutes
        self._token: Optional[str] = None
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.gcli_url = data.get("gcli_url", self.gcli_url)
                self.gcli_password = data.get("gcli_password", self.gcli_password)
                self.auto_connect = data.get("auto_connect", self.auto_connect)
                self.auto_verify_enabled = data.get("auto_verify_enabled", self.auto_verify_enabled)
                self.auto_verify_interval = data.get("auto_verify_interval", self.auto_verify_interval)
                self.auto_verify_error_codes = data.get("auto_verify_error_codes", self.auto_verify_error_codes)
                self.quota_refresh_interval = data.get("quota_refresh_interval", self.quota_refresh_interval)
            except Exception:
                pass

    def save(self):
        data = {
            "gcli_url": self.gcli_url,
            "gcli_password": self.gcli_password,
            "auto_connect": self.auto_connect,
            "auto_verify_enabled": self.auto_verify_enabled,
            "auto_verify_interval": self.auto_verify_interval,
            "auto_verify_error_codes": self.auto_verify_error_codes,
            "quota_refresh_interval": self.quota_refresh_interval,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_dict(self):
        return {
            "gcli_url": self.gcli_url,
            "gcli_password": self.gcli_password,
            "auto_connect": self.auto_connect,
            "auto_verify_enabled": self.auto_verify_enabled,
            "auto_verify_interval": self.auto_verify_interval,
            "auto_verify_error_codes": self.auto_verify_error_codes,
            "quota_refresh_interval": self.quota_refresh_interval,
        }

    @property
    def token(self) -> Optional[str]:
        return self._token

    @token.setter
    def token(self, value: str):
        self._token = value


config = Config()
