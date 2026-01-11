import re
import logging
from datetime import datetime
from typing import Any, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


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
        logger.info("Model stats reset")
