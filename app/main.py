import logging
import asyncio
import re
import pytz
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, ApplicationBuilder

# Import application modules
from app import logger_setup, api_client, data_handler, telegram_poster, openai_translator
from app.config import config_manager
from app.stats_manager import increment_stat, reset_all_stats # Use convenience functions
from app.bot_interface import setup_bot_handlers # Import the handler setup function

# --- Setup ---
logger_setup.setup_logging()
logger = logging.getLogger(__name__)
config_manager.log_loaded_config() # Log the loaded configuration via the manager

# --- Telegram MarkdownV2 Escaping ---
# Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
# Keep this here as run_check uses it for posting. bot_interface has its own copy.
def escape_markdown_v2(text: str) -> str:
    """Escapes text for Telegram MarkdownV2 parsing."""
    if not isinstance(text, str):
        return ""
    # Ensure '.' and '!' are included as per Telegram MarkdownV2 spec
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Use re.sub to escape characters: \[char]
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# --- Core Task ---
async def run_check(bot: Bot):
    """Fetches news, translates new articles, and posts them to Telegram."""
    logger.info("Starting news check run...")
    # Optionally reset stats per run? Or keep them cumulative? Let's keep cumulative for now.
    # reset_all_stats() # Uncomment to reset stats each run

    # 1. Fetch ranking
    ranking_data = None
    try:
        ranking_data = api_client.get_ranking()
        if ranking_data is not None:
            increment_stat("fetches_success")
        else:
            # Handles None case from get_ranking
            increment_stat("fetches_fail")
            logger.error("Could not fetch news ranking (received None). Skipping run.")
            return
    except Exception as e:
        increment_stat("fetches_fail")
        logger.exception(f"Error fetching news ranking: {e}. Skipping run.")
        return # Exit if fetch fails critically

    if not ranking_data: # Handles empty list case
        logger.info("No articles found in ranking. Skipping run.")
        # Don't count this as a failure, just no data
        return

    # 2. Load already posted articles
    posted_articles_file = config_manager.get("posted_articles_file")
    posted_articles = data_handler.load_posted_articles(posted_articles_file)
    logger.info(f"Loaded {len(posted_articles)} previously posted article URLs.")

    # 3. Identify new articles
    new_articles = [
        article for article in ranking_data
        # Use 'link' key for URL and check if it's already posted
        if isinstance(article, dict) and 'link' in article and article['link'] not in posted_articles
    ]

    if not new_articles:
        logger.info("No new articles found in the ranking.")
        return

    logger.info(f"Found {len(new_articles)} new articles to process.")

    # 4. Process each new article
    processed_count = 0
    for article in new_articles:
        article_link = article.get('link') # Use 'link' key
        if not article_link: # Skip if link is missing for some reason
            logger.warning(f"Article missing 'link', skipping: {article.get('title', 'N/A')}")
            continue
        original_title = article.get('title', 'No Title Provided')
        logger.info(f"Processing new article: {original_title} ({article_link})")

        # --- Fetch Article Content ---
        content_data = api_client.get_article_content(article_link)
        original_body = ""
        if content_data and 'body' in content_data:
            body_text = content_data['body']
            if body_text and isinstance(body_text, str):
                original_body = body_text
            else:
                logger.warning(f"Article body is empty or not a string for {article_link}.")
        else:
            logger.warning(f"Could not get body content for {article_link}.")
            # Don't skip yet, maybe translation can work with title only? Or maybe skip?
            # Let's skip if body is essential for translation/posting quality.
            # increment_stat("fetches_fail") # Or a different stat?
            continue # Skip this article if body is not found

        # 5. Translate Title, Body and Generate Hashtags using OpenAI
        translation_result = None
        try:
            logger.info(f"--> Calling OpenAI translator for: {article_link}")
            translation_result = await openai_translator.translate_and_summarize_article(
                title=original_title,
                body=original_body
            )
            logger.info(f"<-- Returned from OpenAI translator for: {article_link}. Result: {'Success' if translation_result else 'Failure'}")
            if translation_result:
                increment_stat("translations_success")
            else:
                increment_stat("translations_fail")
                logger.error(f"Failed to get translation/hashtags from OpenAI for {article_link}. Skipping article.")
                continue # Skip this article if OpenAI call fails
        except Exception as e:
            increment_stat("translations_fail")
            logger.exception(f"Error during OpenAI translation for {article_link}: {e}. Skipping article.")
            continue

        translated_title = translation_result.get('translated_title', '')
        translated_body = translation_result.get('translated_body', '')
        hashtags = translation_result.get('hashtags', [])

        if not translated_title: # Title is essential
             logger.error(f"OpenAI did not return a translated title for {article_link}. Skipping article.")
             # Already counted as translation fail above
             continue

        # --- Check for Skip Keywords in Hashtags ---
        should_skip = False
        skip_keywords = config_manager.get("skip_keywords", [])
        if skip_keywords:
            for tag in hashtags:
                tag_lower = tag.lower()
                for keyword in skip_keywords:
                    if keyword in tag_lower:
                        logger.info(f"Skipping article '{original_title}' ({article_link}) due to keyword '{keyword}' found in hashtag '{tag}'.")
                        should_skip = True
                        increment_stat("skips_keyword") # Increment skip counter
                        break
                if should_skip:
                    break

        # 6. Format Message (only if not skipping)
        message = ""
        if not should_skip:
            # Escape necessary components for MarkdownV2
            escaped_title = escape_markdown_v2(translated_title)
            # Link in [text](link) doesn't need escaping usually, but other parts do
            # escaped_link = escape_markdown_v2(article_link) # Reverted based on user feedback
            escaped_content = escape_markdown_v2(translated_body)

            # --- Format Publication Time ---
            formatted_time_str = ""
            publication_time_iso = content_data.get('publication_time', '') if content_data else ''
            if publication_time_iso:
                try:
                    if publication_time_iso.endswith('Z'):
                         publication_time_iso = publication_time_iso[:-1] + '+00:00'
                    utc_time = datetime.fromisoformat(publication_time_iso)
                    if utc_time.tzinfo is None:
                        utc_time = utc_time.replace(tzinfo=pytz.utc)
                    jst = pytz.timezone('Asia/Tokyo')
                    jst_time = utc_time.astimezone(jst)
                    formatted_time_str = jst_time.strftime('%Y-%m-%d %H:%M')
                except Exception as time_e:
                     logger.error(f"Could not parse/format publication time '{publication_time_iso}': {time_e}")

            escaped_time = escape_markdown_v2(formatted_time_str)

            # --- Assemble Message Components ---
            title_part = f"*{escaped_title}*\n\n"
            content_part = f"{escaped_content}\n\n" if escaped_content else ""
            link_part = f"[原文链接]({article_link})"
            time_part = f"\n_{escaped_time}_" if escaped_time else ""

            hashtags_part = ""
            if hashtags:
                valid_hashtags = [f"#{tag.lstrip('#')}" for tag in hashtags if isinstance(tag, str) and tag]
                if valid_hashtags:
                    escaped_tags = [escape_markdown_v2(tag) for tag in valid_hashtags]
                    hashtags_part = "\n\n" + " ".join(escaped_tags)

            # --- Calculate Lengths and Truncate Body if Needed ---
            MAX_TELEGRAM_MESSAGE_LENGTH = 4096
            TRUNCATION_SUFFIX = escape_markdown_v2("(未完，请看原文)") # Suffix for truncated body

            # Calculate length of non-body parts
            fixed_parts_length = len(title_part) + len(link_part) + len(time_part) + len(hashtags_part)

            # Calculate maximum allowed length for the body content
            max_content_length = MAX_TELEGRAM_MESSAGE_LENGTH - fixed_parts_length - len(TRUNCATION_SUFFIX)

            # Truncate the content_part if it makes the total message too long
            if escaped_content and len(content_part) > max_content_length:
                 if max_content_length > 0:
                    # Truncate the original escaped_content string
                    truncated_escaped_content = escaped_content[:max_content_length] + TRUNCATION_SUFFIX
                    # Recreate the content_part with the truncated version
                    content_part = f"{truncated_escaped_content}\n\n"
                    logger.warning(f"Message body for {article_link} was too long. Truncated body content.")
                 else:
                    # Edge case: Fixed parts alone are too long or leave no space for body
                    content_part = "" # Remove body entirely if no space
                    logger.warning(f"Message for {article_link} too long even without body. Removing body content.")


            # --- Construct Final Message ---
            message = title_part + content_part + link_part + time_part + hashtags_part

        # 7. Post to Telegram (conditionally)
        message_id = None
        post_success = False
        if not should_skip:
            if message:
                logger.debug(f"Formatted message for {article_link}:\n{message}")
                try:
                    # Pass the bot instance here
                    message_id = await telegram_poster.post_message(bot, message)
                    if message_id is not None:
                        increment_stat("posts_success")
                        post_success = True
                    else:
                        increment_stat("posts_fail")
                        logger.error(f"Failed to post article to Telegram (received None message_id): {article_link}")
                except Exception as e:
                    increment_stat("posts_fail")
                    logger.exception(f"Error posting message for {article_link}: {e}")
            else:
                 increment_stat("posts_fail") # Count as failure if message is empty
                 logger.error(f"Message formatting resulted in empty message for {article_link}. Cannot post.")
        # If should_skip is True, message_id remains None, post_success remains False

        # 8. Update posted articles file (conditionally)
        # Only add if skipped OR if posting was attempted and successful
        if should_skip or post_success:
            logger.info(f"Adding article to posted list. Skipped: {should_skip}, Message ID: {message_id}, URL: {article_link}")
            data_handler.add_posted_article(
                filepath=config_manager.get("posted_articles_file"),
                url=article_link,
                title=original_title,
                message_id=message_id, # Will be None if skipped
                skipped=should_skip
            )
        elif not should_skip and not post_success:
            logger.warning(f"Article posting failed and was not skipped. NOT adding to posted list. URL: {article_link}")

        if post_success:
             processed_count += 1 # Increment only if successfully posted

        # A small delay between processing articles within a run
        await asyncio.sleep(5) # Keep the 5-second delay

    logger.info(f"--- run_check function finished. Processed {processed_count} new articles this run. ---")


# --- Background Task for Scheduled Checks ---
async def scheduled_news_check(application: Application):
    """Runs the news check periodically."""
    interval_minutes = config_manager.get("schedule_interval_minutes", 10)
    interval_seconds = interval_minutes * 60
    logger.info(f"News check scheduled to run every {interval_minutes} minutes ({interval_seconds} seconds).")

    # Run once immediately at startup after a short delay to allow bot connection
    logger.info("Running initial news check shortly after startup...")
    await asyncio.sleep(10) # Wait 10 seconds before first check
    try:
        await run_check(application.bot)
    except Exception as e:
        logger.exception("Error during initial news check run.")

    # Then run in a loop
    while True:
        await asyncio.sleep(interval_seconds)
        logger.info(f"Scheduled interval ({interval_minutes} min) elapsed. Running news check...")
        try:
            await run_check(application.bot)
        except Exception as e:
            logger.exception("Error during scheduled news check run.")


# --- Main Application Setup and Run ---
async def main():
    """Sets up and runs the Telegram bot and the scheduled news checker."""
    logger.info("Starting application setup...")

    # Ensure essential config is present before building app
    bot_token = config_manager.get("telegram_bot_token")
    if not bot_token:
        logger.critical("Telegram Bot Token not found in configuration. Exiting.")
        return # Cannot proceed without token

    # Build the Telegram Application
    logger.info("Building Telegram application...")
    application = ApplicationBuilder().token(bot_token).build()

    # Add command handlers (e.g., /stats)
    setup_bot_handlers(application)

    # Start configuration file watcher in a separate thread
    logger.info("Starting configuration file watcher...")
    config_manager.start_watching()

    # Run the application and the background task concurrently
    try:
        logger.info("Starting bot polling and scheduled news checker...")
        async with application: # Manages startup and shutdown of bot components
            await application.initialize() # Initialize handlers, etc.
            await application.start()      # Start network connections
            await application.updater.start_polling() # Start fetching updates

            # Create and run the background news check task
            news_check_task = asyncio.create_task(scheduled_news_check(application))
            logger.info("Application started successfully. Waiting for tasks...")

            # Keep the main function alive until tasks are done or interrupted
            # In this case, news_check_task runs forever until cancelled
            await news_check_task # This will run indefinitely

    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main execution: {e}")
    finally:
        logger.info("Starting shutdown process...")
        # Stop the configuration watcher
        logger.info("Stopping configuration file watcher...")
        config_manager.stop_watching()

        # Application shutdown is handled by 'async with application:' context manager
        # It calls application.stop(), application.updater.stop(), application.shutdown()

        logger.info("Application shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())