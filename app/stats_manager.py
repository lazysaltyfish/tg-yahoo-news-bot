import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Stats:
    """Data class to hold runtime statistics."""
    fetches_success: int = 0
    fetches_fail: int = 0
    translations_success: int = 0
    translations_fail: int = 0
    posts_success: int = 0
    posts_fail: int = 0
    skips_keyword: int = 0

@dataclass
class DailyStats:
    """Data class to hold per-day statistics."""
    total: int = 0
    success: int = 0
    fail: int = 0
    skipped: int = 0

class StatsManager:
    """Manages runtime statistics for the bot."""

    def __init__(self):
        self._stats = Stats()
        self._daily_stats: dict[str, DailyStats] = {}
        self._daily_order: list[str] = []
        self._max_daily_days = 7
        # Using a lock to ensure thread-safety if stats are accessed/modified
        # from different async tasks or threads concurrently.
        self._lock = threading.Lock()
        logger.info("Statistics Manager initialized.")

    def increment(self, stat_name: str):
        """Increments a specific statistic counter safely."""
        with self._lock:
            if hasattr(self._stats, stat_name):
                current_value = getattr(self._stats, stat_name)
                setattr(self._stats, stat_name, current_value + 1)
                # logger.debug(f"Incremented stat '{stat_name}' to {current_value + 1}")
            else:
                logger.warning(f"Attempted to increment non-existent stat: {stat_name}")

    def _get_or_create_day(self, date_key: str) -> DailyStats:
        if date_key not in self._daily_stats:
            self._daily_stats[date_key] = DailyStats()
            self._daily_order.append(date_key)
            self._prune_old_days()
        return self._daily_stats[date_key]

    def _prune_old_days(self):
        while len(self._daily_order) > self._max_daily_days:
            old_key = self._daily_order.pop(0)
            self._daily_stats.pop(old_key, None)

    def increment_daily(self, date_key: str, field_name: str):
        """Increments a specific per-day statistic counter safely."""
        with self._lock:
            day_stats = self._get_or_create_day(date_key)
            if hasattr(day_stats, field_name):
                current_value = getattr(day_stats, field_name)
                setattr(day_stats, field_name, current_value + 1)
            else:
                logger.warning(f"Attempted to increment non-existent daily stat: {field_name}")

    def get_stats(self) -> Stats:
        """Returns a copy of the current statistics."""
        with self._lock:
            # Return a copy to prevent external modification of the internal state
            return Stats(**self._stats.__dict__)

    def get_daily_stats(self, last_days: int = 7) -> list[tuple[str, DailyStats]]:
        """Returns a list of (date_key, DailyStats) for the most recent days."""
        with self._lock:
            start_index = max(0, len(self._daily_order) - last_days)
            keys = self._daily_order[start_index:]
            return [(key, DailyStats(**self._daily_stats[key].__dict__)) for key in keys]

    def reset_stats(self):
        """Resets all statistics counters to zero."""
        with self._lock:
            self._stats = Stats()
            self._daily_stats = {}
            self._daily_order = []
            logger.info("Runtime statistics reset.")

# --- Singleton Instance ---
# Provide a single instance for the application to use
stats_manager = StatsManager()

# --- Convenience Functions ---
# Optional: Provide module-level functions that wrap the singleton instance methods

def increment_stat(stat_name: str):
    """Module-level convenience function to increment a stat."""
    stats_manager.increment(stat_name)

def get_current_stats() -> Stats:
    """Module-level convenience function to get current stats."""
    return stats_manager.get_stats()

def increment_daily_stat(date_key: str, field_name: str):
    """Module-level convenience function to increment a daily stat."""
    stats_manager.increment_daily(date_key, field_name)

def get_daily_stats(last_days: int = 7) -> list[tuple[str, DailyStats]]:
    """Module-level convenience function to get daily stats."""
    return stats_manager.get_daily_stats(last_days=last_days)

def reset_all_stats():
    """Module-level convenience function to reset stats."""
    stats_manager.reset_stats()
