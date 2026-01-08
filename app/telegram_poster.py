import logging
import asyncio
from urllib.parse import urlparse, urlunparse # Add this import
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest # Import BadRequest specifically
from .config import config_manager

logger = logging.getLogger(__name__)

# Telegram API limits
CAPTION_MAX_LENGTH = 1024  # Max length for photo captions
TEXT_MAX_LENGTH = 4096     # Max length for text messages

# Initialize the Bot instance globally? Or per function call?
# Initializing per call might be slightly less efficient but avoids potential
# issues with async event loops if the main script structure changes.
# Let's initialize per call for simplicity here.

async def post_message(bot: Bot, title: str, body: str = "", image_url: str = None):
    """
    Sends a message (text or photo with caption) to the configured Telegram channel.
    If the message with an image is too long, it splits it into two messages:
    1. Image + Title (caption potentially truncated if title itself is too long)
    2. Title + Body (full text, potentially truncated if it exceeds text message limits)

    Args:
        bot: The initialized telegram.Bot instance.
        title: The title of the message.
        body: Optional body of the message.
        image_url: Optional URL of the image to send.

    Returns:
        The message_id of the sent message (or the second message if split) if successful, None otherwise.
    """
    # Get channel ID from config
    channel_id = config_manager.get("telegram_channel_id")

    if not channel_id:
        logger.error("Telegram Channel ID is not configured. Cannot send message.")
        return None # Return None for consistency with other error returns
    if not bot:
        logger.error("Telegram Bot instance was not provided. Cannot send message.")
        return None

    if not title: # Changed from message to title
        logger.warning("Attempted to send a message with an empty title to Telegram.")
        return None

    # Bot instance is now passed in
    logger.debug(f"Attempting to send message to Telegram channel {channel_id} using provided bot instance...")

    # Construct the full message text
    full_message_text = title
    if body and body.strip(): # Ensure body is not empty or just whitespace
        full_message_text = f"{title}\n\n{body}" # Using double newline for better separation

    try:
        if image_url:
            # Remove query parameters from image_url to avoid issues with some Telegram clients/APIs
            parsed_url = urlparse(image_url)
            image_url = urlunparse(parsed_url._replace(query=""))
            logger.debug(f"Cleaned image URL: {image_url}")

            if len(full_message_text) > CAPTION_MAX_LENGTH:
                logger.info(f"Caption for image is too long ({len(full_message_text)} chars, limit {CAPTION_MAX_LENGTH}). Splitting message.")
                
                # Message 1: Photo + Title (caption)
                caption_for_photo = title
                if len(title) > CAPTION_MAX_LENGTH:
                    logger.warning(f"Title itself ({len(title)} chars) exceeds CAPTION_MAX_LENGTH ({CAPTION_MAX_LENGTH}). Truncating for photo caption.")
                    caption_for_photo = title[:CAPTION_MAX_LENGTH]
                
                sent_photo_msg = await bot.send_photo(
                    chat_id=channel_id,
                    photo=image_url,
                    caption=caption_for_photo,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info(f"Successfully sent photo part (ID: {sent_photo_msg.message_id}) to {channel_id}.")

                # Message 2: Title + Body (text)
                text_for_second_message = full_message_text
                if len(full_message_text) > TEXT_MAX_LENGTH:
                    logger.warning(f"Full text content for second message ({len(full_message_text)} chars) exceeds TEXT_MAX_LENGTH ({TEXT_MAX_LENGTH}). It will be truncated.")
                    text_for_second_message = full_message_text[:TEXT_MAX_LENGTH]
                
                sent_text_msg = await bot.send_message(
                    chat_id=channel_id,
                    text=text_for_second_message,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info(f"Successfully sent text part (ID: {sent_text_msg.message_id}) to {channel_id}.")
                return sent_text_msg.message_id # Return ID of the second message
            else:
                # Caption is not too long, send as a single photo with caption
                logger.info(f"Sending photo with caption (length {len(full_message_text)}) to {channel_id}...")
                sent_message = await bot.send_photo(
                    chat_id=channel_id,
                    photo=image_url,
                    caption=full_message_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info(f"Successfully sent photo (ID: {sent_message.message_id}) to Telegram channel {channel_id}.")
                return sent_message.message_id
        else:
            # No image, send as a text message
            text_to_send = full_message_text
            if len(full_message_text) > TEXT_MAX_LENGTH:
                logger.warning(f"Text message content ({len(full_message_text)} chars) exceeds TEXT_MAX_LENGTH ({TEXT_MAX_LENGTH}). It will be truncated.")
                text_to_send = full_message_text[:TEXT_MAX_LENGTH]

            logger.info(f"Sending text message (length {len(text_to_send)}) to {channel_id}...")
            sent_message = await bot.send_message(
                chat_id=channel_id,
                text=text_to_send,
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
        # Updated logging for title and body
        log_message += f"\nProblematic title:\n---\n{title}\n---"
        if body and body.strip():
             log_message += f"\nProblematic body:\n---\n{body}\n---"
        else:
             log_message += f"\nBody was empty or whitespace.\n---"
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