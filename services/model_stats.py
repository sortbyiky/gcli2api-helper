import json
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)

# Stats file paths
STATS_FILE = Path(__file__).parent.parent / "model_stats.json"
HISTORY_FILE = Path(__file__).parent.parent / "model_stats_history.json"

# History retention settings
HOURLY_RETENTION_HOURS = 24  # Keep last 24 hours
DAILY_RETENTION_DAYS = 30    # Keep last 30 days


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

        # History data
        self._hourly_history: List[Dict] = []
        self._daily_history: List[Dict] = []
        self._current_hour_stats = self._create_empty_period_stats()
        self._current_day_stats = self._create_empty_period_stats()
        self._last_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        self._last_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Pattern to extract model from stream start log
        self._model_pattern = re.compile(
            r"开始接收流式响应，模型:\s*([^\s,]+)"
        )

        # Pattern to extract tokens from stream_end log
        self._token_pattern = re.compile(
            r"input_tokens=(\d+),\s*output_tokens=(\d+)"
        )

        # Load saved stats on init
        self._load()
        self._load_history()

    def _create_empty_period_stats(self) -> Dict:
        """Create empty stats structure for a time period"""
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "models": defaultdict(lambda: {"calls": 0, "tokens": 0})
        }

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

    def _load_history(self):
        """Load history from file"""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._hourly_history = data.get("hourly", [])
                self._daily_history = data.get("daily", [])

                # Load current period stats
                current_hour_data = data.get("current_hour", {})
                current_day_data = data.get("current_day", {})

                if current_hour_data:
                    self._current_hour_stats = {
                        "total_calls": current_hour_data.get("total_calls", 0),
                        "total_tokens": current_hour_data.get("total_tokens", 0),
                        "models": defaultdict(lambda: {"calls": 0, "tokens": 0})
                    }
                    for m, d in current_hour_data.get("models", {}).items():
                        self._current_hour_stats["models"][m] = d

                if current_day_data:
                    self._current_day_stats = {
                        "total_calls": current_day_data.get("total_calls", 0),
                        "total_tokens": current_day_data.get("total_tokens", 0),
                        "models": defaultdict(lambda: {"calls": 0, "tokens": 0})
                    }
                    for m, d in current_day_data.get("models", {}).items():
                        self._current_day_stats["models"][m] = d

                # Load last timestamps
                if data.get("last_hour"):
                    self._last_hour = datetime.fromisoformat(data["last_hour"])
                if data.get("last_day"):
                    self._last_day = datetime.fromisoformat(data["last_day"])

                logger.info(f"Loaded history: {len(self._hourly_history)} hourly, {len(self._daily_history)} daily records")
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")

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

    def _save_history(self):
        """Save history to file"""
        try:
            data = {
                "hourly": self._hourly_history,
                "daily": self._daily_history,
                "current_hour": {
                    "total_calls": self._current_hour_stats["total_calls"],
                    "total_tokens": self._current_hour_stats["total_tokens"],
                    "models": dict(self._current_hour_stats["models"])
                },
                "current_day": {
                    "total_calls": self._current_day_stats["total_calls"],
                    "total_tokens": self._current_day_stats["total_tokens"],
                    "models": dict(self._current_day_stats["models"])
                },
                "last_hour": self._last_hour.isoformat(),
                "last_day": self._last_day.isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

    def _check_and_rotate_periods(self):
        """Check if we need to rotate hourly/daily periods"""
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Rotate hourly
        if current_hour > self._last_hour:
            if self._current_hour_stats["total_calls"] > 0:
                record = {
                    "timestamp": self._last_hour.isoformat(),
                    "total_calls": self._current_hour_stats["total_calls"],
                    "total_tokens": self._current_hour_stats["total_tokens"],
                    "models": dict(self._current_hour_stats["models"])
                }
                self._hourly_history.append(record)

                # Clean old records
                cutoff = now - timedelta(hours=HOURLY_RETENTION_HOURS)
                self._hourly_history = [
                    h for h in self._hourly_history
                    if datetime.fromisoformat(h["timestamp"]) > cutoff
                ]

            self._current_hour_stats = self._create_empty_period_stats()
            self._last_hour = current_hour

        # Rotate daily
        if current_day > self._last_day:
            if self._current_day_stats["total_calls"] > 0:
                record = {
                    "date": self._last_day.strftime("%Y-%m-%d"),
                    "total_calls": self._current_day_stats["total_calls"],
                    "total_tokens": self._current_day_stats["total_tokens"],
                    "models": dict(self._current_day_stats["models"])
                }
                self._daily_history.append(record)

                # Clean old records
                cutoff = now - timedelta(days=DAILY_RETENTION_DAYS)
                self._daily_history = [
                    d for d in self._daily_history
                    if datetime.strptime(d["date"], "%Y-%m-%d") > cutoff
                ]

            self._current_day_stats = self._create_empty_period_stats()
            self._last_day = current_day

    def _record_to_history(self, model_name: str, tokens: int):
        """Record a call to current period stats"""
        self._check_and_rotate_periods()

        # Update hourly
        self._current_hour_stats["total_calls"] += 1
        self._current_hour_stats["total_tokens"] += tokens
        if model_name not in self._current_hour_stats["models"]:
            self._current_hour_stats["models"][model_name] = {"calls": 0, "tokens": 0}
        self._current_hour_stats["models"][model_name]["calls"] += 1
        self._current_hour_stats["models"][model_name]["tokens"] += tokens

        # Update daily
        self._current_day_stats["total_calls"] += 1
        self._current_day_stats["total_tokens"] += tokens
        if model_name not in self._current_day_stats["models"]:
            self._current_day_stats["models"][model_name] = {"calls": 0, "tokens": 0}
        self._current_day_stats["models"][model_name]["calls"] += 1
        self._current_day_stats["models"][model_name]["tokens"] += tokens

        # Save history
        self._save_history()

    def parse_log(self, log_line: str):
        """Parse a log line and extract model usage statistics"""
        try:
            # 1. Check for model start log
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

                model_name = self._current_model or "unknown"

                # Update model stats
                self._stats[model_name]["calls"] += 1
                self._stats[model_name]["tokens"] += total_tokens

                # Update totals
                self._total_calls += 1
                self._total_tokens += total_tokens

                # Record to history
                self._record_to_history(model_name, total_tokens)

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

    def get_history(self, period: str = "hourly", limit: int = 24) -> Dict[str, Any]:
        """Get historical statistics

        Args:
            period: "hourly" or "daily"
            limit: max records to return
        """
        self._check_and_rotate_periods()

        if period == "daily":
            history = self._daily_history[-limit:] if limit else self._daily_history
            current = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "total_calls": self._current_day_stats["total_calls"],
                "total_tokens": self._current_day_stats["total_tokens"],
                "models": dict(self._current_day_stats["models"]),
                "is_current": True
            }
        else:
            history = self._hourly_history[-limit:] if limit else self._hourly_history
            current = {
                "timestamp": self._last_hour.isoformat(),
                "total_calls": self._current_hour_stats["total_calls"],
                "total_tokens": self._current_hour_stats["total_tokens"],
                "models": dict(self._current_hour_stats["models"]),
                "is_current": True
            }

        # Append current period if it has data
        result = list(history)
        if current["total_calls"] > 0:
            result.append(current)

        return {
            "period": period,
            "records": result,
            "total_records": len(result)
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

        # Reset history
        self._hourly_history = []
        self._daily_history = []
        self._current_hour_stats = self._create_empty_period_stats()
        self._current_day_stats = self._create_empty_period_stats()
        self._last_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        self._last_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        self._save()
        self._save_history()
        logger.info("Model stats and history reset")
