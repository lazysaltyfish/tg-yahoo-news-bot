import json
import logging
import os
import fcntl # For file locking on POSIX systems (like Linux in Docker)

logger = logging.getLogger(__name__)

def load_posted_articles(filepath: str) -> dict:
    """
    Loads the dictionary of posted articles from a JSON file.

    Args:
        filepath: The path to the JSON file.

    Returns:
        A dictionary mapping posted article URLs to a sub-dictionary
        containing 'title', 'tg_channel_msg_id', and potentially 'skipped'.
        Returns an empty dictionary if the file doesn't exist or is invalid.
    """
    if not os.path.exists(filepath):
        logger.info(f"Posted articles file not found at {filepath}. Returning empty dict.")
        return {}
    try:
        # Use 'with' for automatic file closing, even if errors occur
        with open(filepath, 'r', encoding='utf-8') as f:
            # Acquire shared lock for reading - allows multiple readers
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
                if not isinstance(data, dict):
                    logger.warning(f"Invalid data format in {filepath}. Expected dict, got {type(data)}. Returning empty dict.")
                    return {}
                logger.debug(f"Loaded {len(data)} posted articles from {filepath}")
                return data
            except json.JSONDecodeError:
                logger.exception(f"Error decoding JSON from {filepath}. Returning empty dict.")
                return {}
            finally:
                # Release the lock
                fcntl.flock(f, fcntl.LOCK_UN)
    except IOError as e:
        logger.exception(f"Could not read posted articles file {filepath}: {e}")
        return {}
    except Exception as e:
        logger.exception(f"An unexpected error occurred loading {filepath}: {e}")
        return {}


def add_posted_article(filepath: str, url: str, title: str, message_id: int | None, skipped: bool):
    """
    Adds a new article URL, title, message ID, and skipped status to the JSON file.
    Uses file locking to prevent race conditions during write.

    Args:
        filepath: The path to the JSON file.
        url: The URL of the article to add.
        title: The title of the article to add.
        message_id: The Telegram message ID, or None if the post was skipped.
        skipped: Boolean indicating if the article posting was skipped due to keywords.
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Open file in read/write mode ('a+' creates if not exists, '+' enables reading)
        # Using 'r+' requires the file to exist, 'w+' truncates, 'a+' appends (not ideal for JSON rewrite)
        # Best approach: read existing, modify, write back exclusively
        # Open with 'a' first to create if not exists, then reopen with 'r+'
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                 # Ensure file exists, create if not. No lock needed here yet.
                 pass
        except IOError as e:
             logger.error(f"Could not ensure file exists at {filepath}: {e}")
             return # Cannot proceed if file cannot be created/accessed

        # Now open for reading and writing with exclusive lock
        with open(filepath, 'r+', encoding='utf-8') as f:
            # Acquire exclusive lock (LOCK_EX). Blocks if another process holds EX or SH lock.
            # Use non-blocking (LOCK_NB) if you want to fail immediately instead of waiting.
            # Here, waiting (blocking) is acceptable.
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                # Read current data
                f.seek(0) # Go to the beginning of the file
                try:
                    current_data = json.load(f)
                    if not isinstance(current_data, dict):
                        logger.warning(f"Data in {filepath} is not a dict ({type(current_data)}). Overwriting with new entry.")
                        current_data = {}
                except json.JSONDecodeError:
                    logger.warning(f"Could not decode JSON from {filepath}. Starting fresh.")
                    current_data = {} # Start fresh if file is empty or corrupt

                # Add new entry
                if url not in current_data:
                    current_data[url] = {
                        "title": title,
                        "tg_channel_msg_id": message_id, # Can be None if skipped
                        "skipped": skipped
                    }
                    log_msg_id = f"(Msg ID: {message_id})" if message_id else "(Skipped)"
                    logger.debug(f"Adding article to {filepath}: {url} {log_msg_id}")
                else:
                    # Optionally update skipped status if already exists? For now, just log.
                    logger.debug(f"Article already exists in {filepath}, not adding again: {url}")
                    return # No need to write if already present

                # Write updated data back
                f.seek(0) # Go back to the beginning
                f.truncate() # Clear the file content before writing
                json.dump(current_data, f, ensure_ascii=False, indent=4) # Write with pretty print

            except IOError as e:
                logger.exception(f"IOError while writing to locked file {filepath}: {e}")
            except Exception as e:
                 logger.exception(f"Unexpected error writing to locked file {filepath}: {e}")
            finally:
                # Always release the lock
                fcntl.flock(f, fcntl.LOCK_UN)

    except PermissionError as e:
        logger.error(
            f"Permission denied when trying to write to {filepath}. "
            f"This often happens with Docker volume mounts. "
            f"Please check the permissions of the host directory mounted to '/data'. "
            f"Error details: {e}"
        )
    except Exception as e:
        # Catch-all for other unexpected errors like directory creation failure
        logger.exception(f"An unexpected error occurred in add_posted_article for {filepath}: {e}")