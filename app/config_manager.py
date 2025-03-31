import yaml
import logging
import os
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Manages loading, accessing, and live reloading of configuration from a YAML file.
    """
    def __init__(self, config_path='config.yaml', defaults=None, required_keys=None):
        self.config_path = os.path.abspath(config_path)
        self.defaults = defaults if defaults is not None else {}
        self.required_keys = set(required_keys) if required_keys is not None else set()
        self._config = {}
        self._lock = threading.Lock()
        self._observer = None
        self._observer_thread = None
        self._stop_event = threading.Event()

        self._load_config() # Initial load

    def _load_config(self):
        """Loads configuration from the YAML file, merges with defaults, and validates."""
        new_config = self.defaults.copy()
        try:
            logger.info(f"Attempting to load configuration from: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)
                if loaded_config: # Check if file is not empty
                    # Ensure loaded keys are strings if they are not already
                    loaded_config = {str(k): v for k, v in loaded_config.items()}
                    new_config.update(loaded_config)
                else:
                    logger.warning(f"Configuration file is empty or invalid: {self.config_path}. Using defaults.")

            # Type conversions and specific defaults handling (similar to original config.py)
            # Example: Ensure numeric types are correct
            try:
                new_config['schedule_interval_minutes'] = int(new_config.get('schedule_interval_minutes', self.defaults.get('schedule_interval_minutes')))
            except (ValueError, TypeError):
                logger.warning(f"Invalid schedule_interval_minutes. Using default: {self.defaults.get('schedule_interval_minutes')}")
                new_config['schedule_interval_minutes'] = self.defaults.get('schedule_interval_minutes')

            try:
                new_config['openai_max_tokens'] = int(new_config.get('openai_max_tokens', self.defaults.get('openai_max_tokens')))
            except (ValueError, TypeError):
                logger.warning(f"Invalid openai_max_tokens. Using default: {self.defaults.get('openai_max_tokens')}")
                new_config['openai_max_tokens'] = self.defaults.get('openai_max_tokens')

            try:
                new_config['openai_temperature'] = float(new_config.get('openai_temperature', self.defaults.get('openai_temperature')))
            except (ValueError, TypeError):
                logger.warning(f"Invalid openai_temperature. Using default: {self.defaults.get('openai_temperature')}")
                new_config['openai_temperature'] = self.defaults.get('openai_temperature')

            # Handle list type for skip_keywords
            skip_keywords = new_config.get('skip_keywords')
            if isinstance(skip_keywords, list):
                 new_config['skip_keywords'] = [str(kw).strip().lower() for kw in skip_keywords if kw and isinstance(kw, str)]
            elif skip_keywords is not None: # If it exists but isn't a list
                 logger.warning(f"Invalid format for skip_keywords (expected a list). Ignoring. Value: {skip_keywords}")
                 new_config['skip_keywords'] = [] # Default to empty list
            else:
                 new_config['skip_keywords'] = [] # Default if not present


            # Validation
            missing_keys = self.required_keys - set(new_config.keys())
            # Also check if required keys have None or empty string values (adjust as needed)
            empty_required_keys = {k for k in self.required_keys if new_config.get(k) is None or new_config.get(k) == ""}

            if missing_keys or empty_required_keys:
                 all_missing = missing_keys.union(empty_required_keys)
                 logger.error(f"Missing or empty required configuration keys: {', '.join(all_missing)}")
                 # Decide on behavior: raise error or just log? Let's log and continue with potentially broken state for now.
                 # raise ValueError(f"Missing or empty required configuration keys: {', '.join(all_missing)}")

            with self._lock:
                self._config = new_config
            logger.info("Configuration loaded successfully.")
            # Log loaded config (excluding secrets) - can be called from outside if needed
            # self.log_loaded_config()

        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}. Using defaults only.")
            # Proceed with defaults, validation will likely fail if required keys are not in defaults
            with self._lock:
                self._config = new_config # Still store defaults
            missing_keys = self.required_keys - set(self._config.keys())
            if missing_keys:
                 logger.error(f"Missing required configuration keys (file not found): {', '.join(missing_keys)}")
                 # raise FileNotFoundError(f"Config file {self.config_path} not found and defaults missing required keys: {', '.join(missing_keys)}")

        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file {self.config_path}: {e}. Using previously loaded config or defaults.")
            # Keep the old config if available, otherwise just defaults
            if not self._config: # If first load failed
                 with self._lock:
                     self._config = self.defaults.copy()
                 logger.warning("Falling back to default configuration due to YAML parsing error on initial load.")

        except Exception as e:
            logger.exception(f"An unexpected error occurred while loading configuration: {e}")
            # Keep the old config if available
            if not self._config:
                 with self._lock:
                     self._config = self.defaults.copy()
                 logger.warning("Falling back to default configuration due to unexpected error on initial load.")


    def get(self, key, default=None):
        """Gets a configuration value thread-safely."""
        with self._lock:
            # Return a copy for mutable types like lists to prevent modification
            value = self._config.get(key, default)
            if isinstance(value, (list, dict)):
                return value.copy()
            return value

    def _reload_config(self):
        """Called when the config file changes."""
        logger.info(f"Detected change in {self.config_path}. Reloading configuration...")
        try:
            self._load_config()
            logger.info("Configuration reloaded successfully.")
            # Optionally: Add a hook/callback mechanism here if specific modules
            # need to react immediately to changes (e.g., re-init logging)
            # For now, modules will get updated values on their next call to get().
        except Exception as e:
            logger.exception(f"Error reloading configuration: {e}. Previous configuration remains active.")

    def start_watching(self):
        """Starts monitoring the configuration file in a background thread."""
        if self._observer_thread and self._observer_thread.is_alive():
            logger.warning("Configuration watcher thread already running.")
            return

        logger.info(f"Starting configuration file watcher for: {self.config_path}")
        event_handler = _ConfigChangeHandler(self._reload_config, self.config_path)
        self._observer = Observer()
        config_dir = os.path.dirname(self.config_path)
        self._observer.schedule(event_handler, config_dir, recursive=False)

        self._stop_event.clear()
        self._observer_thread = threading.Thread(target=self._run_observer, daemon=True)
        self._observer_thread.start()

    def _run_observer(self):
        """Runs the watchdog observer loop."""
        self._observer.start()
        logger.info("Watchdog observer started.")
        try:
            while not self._stop_event.is_set():
                time.sleep(1) # Keep thread alive while observer runs
        except Exception as e:
             logger.exception(f"Error in watchdog observer thread: {e}")
        finally:
            self._observer.stop()
            self._observer.join()
            logger.info("Watchdog observer stopped.")


    def stop_watching(self):
        """Stops monitoring the configuration file."""
        if self._observer_thread and self._observer_thread.is_alive():
            logger.info("Stopping configuration file watcher...")
            self._stop_event.set()
            # Observer is stopped in the _run_observer finally block
            self._observer_thread.join(timeout=5) # Wait for thread to finish
            if self._observer_thread.is_alive():
                 logger.warning("Watcher thread did not stop gracefully.")
            self._observer = None
            self._observer_thread = None
            logger.info("Configuration file watcher stopped.")
        else:
            logger.info("Configuration file watcher not running.")

    def log_loaded_config(self):
        """Logs the currently loaded configuration values (excluding secrets)."""
        # Be careful about logging sensitive data!
        log_config = {}
        with self._lock:
            log_config = self._config.copy() # Work on a copy

        sensitive_keys = {'telegram_bot_token', 'openai_api_key'}
        log_output = "--- Current Configuration ---"
        for key, value in sorted(log_config.items()):
            if key in sensitive_keys:
                log_output += f"\n{key}: {'Set' if value else 'Not Set'}"
            else:
                log_output += f"\n{key}: {value}"
        log_output += "\n---------------------------"
        logger.info(log_output)


class _ConfigChangeHandler(FileSystemEventHandler):
    """Handles file system events for the configuration file."""
    def __init__(self, reload_callback, target_path):
        self._reload_callback = reload_callback
        self._target_path = os.path.abspath(target_path)
        self._last_event_time = 0
        self._debounce_seconds = 1.0 # Avoid rapid firing for single saves

    def on_modified(self, event):
        """Called when a file or directory is modified."""
        if isinstance(event, FileModifiedEvent) and os.path.abspath(event.src_path) == self._target_path:
            current_time = time.time()
            # Debounce: Check if enough time has passed since the last event
            if current_time - self._last_event_time > self._debounce_seconds:
                logger.debug(f"Modification detected for target config file: {event.src_path}")
                self._last_event_time = current_time
                self._reload_callback()
            else:
                 logger.debug(f"Debounced modification event for: {event.src_path}")

    # Optionally handle 'created' if the file might be created after startup
    def on_created(self, event):
         if os.path.abspath(event.src_path) == self._target_path:
             current_time = time.time()
             if current_time - self._last_event_time > self._debounce_seconds:
                 logger.info(f"Target config file created: {event.src_path}. Triggering reload.")
                 self._last_event_time = current_time
                 self._reload_callback()
             else:
                 logger.debug(f"Debounced creation event for: {event.src_path}")