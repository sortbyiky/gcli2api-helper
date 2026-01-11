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
        self._current_model = None  # Track current model for correlation

        # Pattern to extract model from stream start log
        # Example: [ANTIGRAVITY STREAM] 开始接收流式响应，模型: claude-opus-4-5-thinking
        self._model_pattern = re.compile(
            r"开始接收流式响应，模型:\s*([^\s,]+)"
        )

        # Pattern to extract tokens from stream_end log
        # Example: input_tokens=1011, output_tokens=5
        self._token_pattern = re.compile(
            r"input_tokens=(\d+),\s*output_tokens=(\d+)"
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
            # 1. Check for model start log (开始接收流式响应)
            model_match = self._model_pattern.search(log_line)
            if model_match:
                self._current_model = model_match.group(1).strip()
                logger.debug(f"Detected model: {self._current_model}")
                return

            # 2. Check for stream_end log with token info
            token_match = self._token_pattern.search(log_line)
            if token_match:
                input_tokens = int(token_match.group(1))
                output_tokens = int(token_match.group(2))
                total_tokens = input_tokens + output_tokens

                # Use current model or fallback to "unknown"
                model_name = self._current_model or "unknown"

                # Update model stats
                self._stats[model_name]["calls"] += 1
                self._stats[model_name]["tokens"] += total_tokens

                # Update totals
                self._total_calls += 1
                self._total_tokens += total_tokens

                # Save to file
                self._save()

                logger.debug(f"Parsed: {model_name} - {total_tokens} tokens (in={input_tokens}, out={output_tokens})")
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
