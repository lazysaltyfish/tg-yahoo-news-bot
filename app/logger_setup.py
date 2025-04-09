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

    # Apply specific log levels from configuration
    specific_levels = config_manager.get("log_levels", {})
    if isinstance(specific_levels, dict):
        for module_name, level_str in specific_levels.items():
            level_str_upper = str(level_str).upper()
            specific_log_level = getattr(logging, level_str_upper, None)
            if specific_log_level is not None:
                try:
                    module_logger = logging.getLogger(str(module_name))
                    module_logger.setLevel(specific_log_level)
                    # Optional: Log the specific level being applied
                    # Use the root logger to ensure this message appears based on root level
                    logging.info(f"Applied specific log level {level_str_upper} to logger '{module_name}'")
                except Exception as e:
                    logging.warning(f"Error applying specific log level for '{module_name}': {e}")
            else:
                logging.warning(f"Invalid log level '{level_str}' specified for logger '{module_name}'. Skipping.")
    elif specific_levels: # If it exists but is not a dict
         logging.warning(f"Invalid format for 'log_levels' in config (expected a dictionary). Ignoring specific levels. Value: {specific_levels}")


    # Suppress overly verbose logs from libraries if needed (optional)
    # logging.getLogger("requests").setLevel(logging.WARNING)
    # logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info(f"Root logging level configured: {log_level_str}")