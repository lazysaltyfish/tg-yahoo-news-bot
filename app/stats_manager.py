import logging
import threading
from dataclasses import dataclass, field

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

class StatsManager:
    """Manages runtime statistics for the bot."""

    def __init__(self):
        self._stats = Stats()
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

    def get_stats(self) -> Stats:
        """Returns a copy of the current statistics."""
        with self._lock:
            # Return a copy to prevent external modification of the internal state
            return Stats(**self._stats.__dict__)

    def reset_stats(self):
        """Resets all statistics counters to zero."""
        with self._lock:
            self._stats = Stats()
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

def reset_all_stats():
    """Module-level convenience function to reset stats."""
    stats_manager.reset_stats()