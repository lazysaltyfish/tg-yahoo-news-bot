import logging
import sys
from .config import config_manager

def setup_logging():
    """Configures the root logger."""
    log_level_str = config_manager.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO) # Default to INFO if invalid level

    # Define the log format
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicate logs if setup is called multiple times
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create a handler for console output (stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)

    # Create a formatter and set it for the handler
    formatter = logging.Formatter(log_format, datefmt=date_format)
    stream_handler.setFormatter(formatter)

    # Add the handler to the root logger
    logger.addHandler(stream_handler)

    # Suppress overly verbose logs from libraries if needed (optional)
    # logging.getLogger("requests").setLevel(logging.WARNING)
    # logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info(f"Logging configured with level: {log_level_str}")