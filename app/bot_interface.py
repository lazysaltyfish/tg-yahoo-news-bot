import logging
import re
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, Application
from telegram.constants import ParseMode

# Import necessary components from our application
from app.config import config_manager
from app.stats_manager import get_current_stats, Stats  # Import the Stats dataclass too
from app.data_handler import load_posted_articles

logger = logging.getLogger(__name__)

# --- Telegram MarkdownV2 Escaping ---
# Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
def escape_markdown_v2(text: str) -> str:
    """Escapes text for Telegram MarkdownV2 parsing."""
    if not isinstance(text, str):
        return ""
    # Ensure '.' and '!' are included as per Telegram MarkdownV2 spec
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Use re.sub to escape characters: \[char]
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# --- Command Handler ---

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /stats command, sending back runtime and persistent stats."""
    if not update.effective_user:
        logger.warning("Received /stats command with no effective user.")
        return # Cannot check authorization

    user_id = update.effective_user.id
    logger.info(f"Received /stats command from user ID: {user_id}")

    # 1. Check Authorization
    authorized_user_ids = config_manager.get("authorized_user_ids", [])
    if authorized_user_ids and user_id not in authorized_user_ids:
        logger.warning(f"Unauthorized user {user_id} attempted to use /stats.")
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        return

    # 2. Get Runtime Stats (since last reset/start)
    runtime_stats: Stats = get_current_stats()

    # 3. Get Persistent Stats (from JSON file)
    posted_articles_file = config_manager.get("posted_articles_file")
    posted_data = load_posted_articles(posted_articles_file)

    total_articles_in_db = len(posted_data)
    total_posted_successfully = 0
    total_skipped_in_db = 0
    for article_data in posted_data.values():
        if isinstance(article_data, dict):
            if article_data.get('skipped', False):
                total_skipped_in_db += 1
            # Count as successfully posted only if not skipped and has a message ID
            elif article_data.get('tg_channel_msg_id') is not None:
                 total_posted_successfully += 1

    # 4. Format the Message (using MarkdownV2)
    # Use the escape_markdown_v2 function for text parts
    runtime_header = escape_markdown_v2("Runtime (Since Last Start/Reset):")
    fetches_line = escape_markdown_v2(f"  - Fetches: {runtime_stats.fetches_success} success, {runtime_stats.fetches_fail} fail")
    translations_line = escape_markdown_v2(f"  - Translations: {runtime_stats.translations_success} success, {runtime_stats.translations_fail} fail")
    posts_line = escape_markdown_v2(f"  - Posts: {runtime_stats.posts_success} success, {runtime_stats.posts_fail} fail")
    skipped_runtime_line = escape_markdown_v2(f"  - Skipped (Keywords): {runtime_stats.skips_keyword}")

    persistent_header = escape_markdown_v2("Persistent Data (All Time):")
    total_db_line = escape_markdown_v2(f"  - Total Articles in DB: {total_articles_in_db}")
    posted_db_line = escape_markdown_v2(f"  - Successfully Posted: {total_posted_successfully}")
    skipped_db_line = escape_markdown_v2(f"  - Skipped (Keywords) in DB: {total_skipped_in_db}")

    message_lines = [
        "*📊 Bot Statistics*", # Keep Markdown syntax as is
        "",
        f"*{runtime_header}*", # Apply Markdown after escaping text
        fetches_line,
        translations_line,
        posts_line,
        skipped_runtime_line,
        "",
        f"*{persistent_header}*", # Apply Markdown after escaping text
        total_db_line,
        posted_db_line,
        skipped_db_line,
    ]
    message = "\n".join(message_lines)

    # 5. Send Reply
    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Sent stats report to user ID: {user_id}")
    except Exception as e:
        logger.error(f"Failed to send stats reply to user {user_id}: {e}")
        # Optionally send a plain text error message back
        try:
            await update.message.reply_text("Sorry, there was an error generating the stats report.")
        except Exception:
            logger.error(f"Failed even to send the error message back to user {user_id}.")


# --- Bot Setup ---

def setup_bot_handlers(application: Application):
    """Adds command handlers to the Telegram bot application."""
    stats_handler = CommandHandler("stats", stats_command)

    application.add_handler(stats_handler)
    logger.info("Added /stats command handler.")