import os
import logging

# --- Environment Variable Loading ---

# Required variables
API_BASE_URL = os.environ.get("API_BASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
YAHOO_RANKING_BASE_URL = os.environ.get("YAHOO_RANKING_BASE_URL") # Added for ranking API parameter
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL")
OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL")

# Optional variables with defaults
DEFAULT_POSTED_ARTICLES_FILE = "data/posted_articles.json"
POSTED_ARTICLES_FILE = os.environ.get("POSTED_ARTICLES_FILE", DEFAULT_POSTED_ARTICLES_FILE)

DEFAULT_LOG_LEVEL = "DEBUG"
LOG_LEVEL = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()

DEFAULT_SCHEDULE_INTERVAL_MINUTES = 10
try:
    SCHEDULE_INTERVAL_MINUTES = int(os.environ.get("SCHEDULE_INTERVAL_MINUTES", DEFAULT_SCHEDULE_INTERVAL_MINUTES))
except ValueError:
    logging.warning(
        f"Invalid SCHEDULE_INTERVAL_MINUTES value. Using default: {DEFAULT_SCHEDULE_INTERVAL_MINUTES} minutes."
    )
    SCHEDULE_INTERVAL_MINUTES = DEFAULT_SCHEDULE_INTERVAL_MINUTES

DEFAULT_OPENAI_MAX_TOKENS = 1000
try:
    OPENAI_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", DEFAULT_OPENAI_MAX_TOKENS))
except ValueError:
    logging.warning(f"Invalid OPENAI_MAX_TOKENS value. Using default: {DEFAULT_OPENAI_MAX_TOKENS}.")
    OPENAI_MAX_TOKENS = DEFAULT_OPENAI_MAX_TOKENS

DEFAULT_OPENAI_TEMPERATURE = 0.7
try:
    OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", DEFAULT_OPENAI_TEMPERATURE))
except ValueError:
    logging.warning(f"Invalid OPENAI_TEMPERATURE value. Using default: {DEFAULT_OPENAI_TEMPERATURE}.")
    OPENAI_TEMPERATURE = DEFAULT_OPENAI_TEMPERATURE

# --- Validation ---

REQUIRED_VARS = {
    "API_BASE_URL": API_BASE_URL,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHANNEL_ID": TELEGRAM_CHANNEL_ID,
    "YAHOO_RANKING_BASE_URL": YAHOO_RANKING_BASE_URL,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "OPENAI_MODEL": OPENAI_MODEL,
    # OPENAI_API_BASE_URL is optional, no need to validate its presence
}

missing_vars = [name for name, value in REQUIRED_VARS.items() if value is None]

if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# --- Log Loaded Configuration (excluding sensitive data) ---
# Note: Logging setup needs to happen *after* this file is imported but before extensive use.
# We'll log this from main.py after setting up the logger.

def log_config():
    """Logs the loaded configuration values (excluding secrets)."""
    logging.info("--- Configuration ---")
    logging.info(f"API_BASE_URL: {API_BASE_URL}")
    logging.info(f"YAHOO_RANKING_BASE_URL: {YAHOO_RANKING_BASE_URL}")
    logging.info(f"TELEGRAM_BOT_TOKEN: {'Set' if TELEGRAM_BOT_TOKEN else 'Not Set'}")
    logging.info(f"TELEGRAM_CHANNEL_ID: {'Set' if TELEGRAM_CHANNEL_ID else 'Not Set'}")
    logging.info(f"POSTED_ARTICLES_FILE: {POSTED_ARTICLES_FILE}")
    logging.info(f"LOG_LEVEL: {LOG_LEVEL}")
    logging.info(f"SCHEDULE_INTERVAL_MINUTES: {SCHEDULE_INTERVAL_MINUTES}")
    logging.info(f"OPENAI_API_KEY: {'Set' if OPENAI_API_KEY else 'Not Set'}")
    logging.info(f"OPENAI_MODEL: {OPENAI_MODEL}")
    logging.info(f"OPENAI_API_BASE_URL: {OPENAI_API_BASE_URL if OPENAI_API_BASE_URL else 'Default'}")
    logging.info(f"OPENAI_MAX_TOKENS: {OPENAI_MAX_TOKENS}")
    logging.info(f"OPENAI_TEMPERATURE: {OPENAI_TEMPERATURE}")
    logging.info("---------------------")