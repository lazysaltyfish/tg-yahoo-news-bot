import logging
from .config_manager import ConfigManager # Use relative import within the app package

logger = logging.getLogger(__name__)

# --- Default Configuration Values ---
# These values are used if not specified in config.yaml
DEFAULT_CONFIG = {
    "posted_articles_file": "data/posted_articles.json",
    "log_level": "DEBUG",
    "schedule_interval_minutes": 10,
    "openai_max_tokens": 1000,
    "openai_temperature": 0.7,
    "skip_keywords": [], # Default to empty list
    "openai_api_base_url": None, # Default to None (use OpenAI default)
    # Required keys don't strictly need defaults here if they MUST be in the file,
    # but providing None helps structure. The manager handles validation.
    "api_base_url": None,
    "telegram_bot_token": None,
    "telegram_channel_id": None,
    "yahoo_ranking_base_urls": [], # Default to empty list
    "openai_api_key": None,
    "openai_model": None,
}

# --- Required Configuration Keys ---
# These keys MUST be present in the final configuration (either in config.yaml or defaults)
# and should have non-empty values. The ConfigManager performs this check.
REQUIRED_KEYS = [
    "api_base_url",
    "telegram_bot_token",
    "telegram_channel_id",
    "yahoo_ranking_base_urls",
    "openai_api_key",
    "openai_model",
]

# --- Configuration File Path ---
# Assumes config.yaml is in the project root directory (where docker-compose.yml is)
CONFIG_FILE_PATH = "config.yaml"

# --- Instantiate the Config Manager ---
# This instance will be imported by other modules
config_manager = ConfigManager(
    config_path=CONFIG_FILE_PATH,
    defaults=DEFAULT_CONFIG,
    required_keys=REQUIRED_KEYS
)

# --- Usage Example (in other modules) ---
# from app.config import config_manager
#
# api_key = config_manager.get("openai_api_key")
# interval = config_manager.get("schedule_interval_minutes")
# keywords = config_manager.get("skip_keywords", []) # Provide default if needed