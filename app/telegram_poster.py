import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest # Import BadRequest specifically
from .config import config_manager

logger = logging.getLogger(__name__)

# Initialize the Bot instance globally? Or per function call?
# Initializing per call might be slightly less efficient but avoids potential
# issues with async event loops if the main script structure changes.
# Let's initialize per call for simplicity here.

async def post_message(bot: Bot, message: str, image_url: str = None):
    """
    Sends a message (text or photo with caption) to the configured Telegram channel.

    Args:
        bot: The initialized telegram.Bot instance.
        message: The text message or caption for the photo. Supports MarkdownV2 formatting.
        image_url: Optional URL of the image to send.

    Returns:
        The message_id of the sent message if successful, None otherwise.
    """
    # Get channel ID from config
    channel_id = config_manager.get("telegram_channel_id")

    if not channel_id:
        logger.error("Telegram Channel ID is not configured. Cannot send message.")
        return None # Return None for consistency with other error returns
    if not bot:
        logger.error("Telegram Bot instance was not provided. Cannot send message.")
        return None

    if not message:
        logger.warning("Attempted to send an empty message to Telegram.")
        return None # Return None for consistency

    # Bot instance is now passed in
    logger.debug(f"Attempting to send message to Telegram channel {channel_id} using provided bot instance...")

    try:
        if image_url:
            logger.info(f"Sending photo with caption to {channel_id}...")
            sent_message = await bot.send_photo(
                chat_id=channel_id,
                photo=image_url,
                caption=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"Successfully sent photo (ID: {sent_message.message_id}) to Telegram channel {channel_id}.")
        else:
            logger.info(f"Sending text message to {channel_id}...")
            sent_message = await bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
                # Consider adding disable_web_page_preview=True if desired
            )
            logger.info(f"Successfully sent text message (ID: {sent_message.message_id}) to Telegram channel {channel_id}.")
        
        return sent_message.message_id
    except BadRequest as e: # Catch BadRequest specifically
        # Log the specific error and the message content
        log_message = f"Telegram BadRequest sending to {channel_id}: {e}"
        if image_url:
            log_message += f"\nImage URL: {image_url}"
        log_message += f"\nProblematic caption/message content:\n---\n{message}\n---"
        logger.error(log_message)
        return None
    except TelegramError as e:
        # Catch other Telegram API errors
        logger.exception(f"Telegram API error sending to {channel_id} (Image URL: {image_url}): {e}")
        if "chat not found" in str(e):
            logger.error("The configured TELEGRAM_CHANNEL_ID might be incorrect or the bot isn't added.")
        elif "bot token is invalid" in str(e):
             logger.error("The configured TELEGRAM_BOT_TOKEN is invalid.")
        # Add more specific error checks if needed, e.g., for invalid image URLs
        return None
    except Exception as e:
        # Catch other potential exceptions
        logger.exception(f"Unexpected error sending via Telegram (Image URL: {image_url}): {e}")
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