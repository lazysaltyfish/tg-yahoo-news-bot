import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest # Import BadRequest specifically
from . import config

logger = logging.getLogger(__name__)

# Initialize the Bot instance globally? Or per function call?
# Initializing per call might be slightly less efficient but avoids potential
# issues with async event loops if the main script structure changes.
# Let's initialize per call for simplicity here.

async def post_message(message: str):
    """
    Sends a message to the configured Telegram channel using the bot token.

    Args:
        message: The text message to send. Supports MarkdownV2 formatting.

    Returns:
        The message_id of the sent message if successful, None otherwise.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHANNEL_ID:
        logger.error("Telegram Bot Token or Channel ID is not configured. Cannot send message.")
        return False

    if not message:
        logger.warning("Attempted to send an empty message to Telegram.")
        return False

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    logger.info(f"Attempting to send message to Telegram channel {config.TELEGRAM_CHANNEL_ID}...")

    try:
        # Note: Sending messages requires an async context if using python-telegram-bot v20+
        # The main loop will need to handle the async execution.
        # Store the returned Message object
        sent_message = await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2 # Use MarkdownV2 for formatting
            # Consider adding disable_web_page_preview=True if desired
        )
        logger.info(f"Successfully sent message (ID: {sent_message.message_id}) to Telegram channel {config.TELEGRAM_CHANNEL_ID}.")
        # Return the message_id
        return sent_message.message_id
    except BadRequest as e: # Catch BadRequest specifically
        # Log the specific error and the message content
        log_message = f"Telegram BadRequest sending message to {config.TELEGRAM_CHANNEL_ID}: {e}"
        log_message += f"\nProblematic message content:\n---\n{message}\n---"
        logger.error(log_message) # Log as error, traceback might not be needed for parsing errors
        # Consider if other specific handling is needed for BadRequest
        return None # Return None on BadRequest
    except TelegramError as e:
        # Catch other Telegram API errors (e.g., invalid token, chat not found, bot blocked)
        logger.exception(f"Telegram API error sending message to {config.TELEGRAM_CHANNEL_ID}: {e}")
        # You might want more specific error handling here based on e.message or e.code
        if "chat not found" in str(e):
            logger.error("The configured TELEGRAM_CHANNEL_ID might be incorrect or the bot isn't added.")
        elif "bot token is invalid" in str(e):
             logger.error("The configured TELEGRAM_BOT_TOKEN is invalid.")
        return None
    except Exception as e:
        # Catch other potential exceptions (network issues, etc.)
        logger.exception(f"Unexpected error sending message via Telegram: {e}")
        return None
    finally:
        # Ensure the bot session is closed if necessary (depends on library version and usage)
        # For v20+, Application.run_polling handles this, but here we use Bot directly.
        # Explicitly closing the bot instance might be needed in some scenarios.
        # await bot.shutdown() # Check if needed for direct Bot usage
        pass

# Example usage (would be called from main.py within an async function)
# async def main_task():
#     # ... other logic ...
#     formatted_message = "..."
#     success = await post_message(formatted_message)
#     if success:
#         # ...
#     else:
#         # ...