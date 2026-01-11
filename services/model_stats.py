import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)

# Stats file path
STATS_FILE = Path(__file__).parent.parent / "model_stats.json"


class ModelStatsService:
    """Service to track model usage statistics from gcli2api logs"""

    def __init__(self):
        self._stats = defaultdict(lambda: {
            "calls": 0,
            "tokens": 0,
        })
        self._total_calls = 0
        self._total_tokens = 0
        self._start_time = datetime.now()

        # Regex pattern to extract model and token info from logs
        # Example: "Model: gemini-2.0-flash-exp | Input: 1000 | Output: 500 | Total: 1500"
        self._pattern = re.compile(
            r"Model:\s*([^\s|]+)\s*\|.*?Total:\s*(\d+)",
            re.IGNORECASE
        )

        # Load saved stats on init
        self._load()

    def _load(self):
        """Load statistics from file"""
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._total_calls = data.get("total_calls", 0)
                self._total_tokens = data.get("total_tokens", 0)
                self._start_time = datetime.fromisoformat(data.get("start_time", datetime.now().isoformat()))
                for model_name, model_data in data.get("models", {}).items():
                    self._stats[model_name] = {
                        "calls": model_data.get("calls", 0),
                        "tokens": model_data.get("tokens", 0),
                    }
                logger.info(f"Loaded model stats: {self._total_calls} calls, {self._total_tokens} tokens")
            except Exception as e:
                logger.warning(f"Failed to load model stats: {e}")

    def _save(self):
        """Save statistics to file"""
        try:
            data = {
                "total_calls": self._total_calls,
                "total_tokens": self._total_tokens,
                "start_time": self._start_time.isoformat(),
                "last_updated": datetime.now().isoformat(),
                "models": {
                    model_name: {
                        "calls": model_data["calls"],
                        "tokens": model_data["tokens"],
                    }
                    for model_name, model_data in self._stats.items()
                }
            }
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save model stats: {e}")

    def parse_log(self, log_line: str):
        """Parse a log line and extract model usage statistics"""
        try:
            match = self._pattern.search(log_line)
            if match:
                model_name = match.group(1).strip()
                total_tokens = int(match.group(2))

                # Update model stats
                self._stats[model_name]["calls"] += 1
                self._stats[model_name]["tokens"] += total_tokens

                # Update totals
                self._total_calls += 1
                self._total_tokens += total_tokens

                # Save to file
                self._save()

                logger.debug(f"Parsed: {model_name} - {total_tokens} tokens")
        except Exception as e:
            logger.debug(f"Failed to parse log line: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        models = {}
        for model_name, data in self._stats.items():
            models[model_name] = {
                "calls": data["calls"],
                "tokens": data["tokens"],
            }

        return {
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "start_time": self._start_time.isoformat(),
            "models": models,
        }

    def reset(self):
        """Reset all statistics"""
        self._stats.clear()
        self._stats = defaultdict(lambda: {
            "calls": 0,
            "tokens": 0,
        })
        self._total_calls = 0
        self._total_tokens = 0
        self._start_time = datetime.now()
        self._save()
        logger.info("Model stats reset")
