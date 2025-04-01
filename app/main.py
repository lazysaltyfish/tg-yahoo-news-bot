import logging
import time
import schedule
import asyncio
import re
import pytz
from datetime import datetime
from app import logger_setup, api_client, data_handler, telegram_poster, openai_translator
from app.config import config_manager

# --- Setup ---
logger_setup.setup_logging()
logger = logging.getLogger(__name__)
config_manager.log_loaded_config() # Log the loaded configuration via the manager

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

# --- Core Task ---
async def run_check():
    """Fetches news, translates new articles, and posts them to Telegram."""
    logger.info("Starting news check run...")

    # 1. Fetch ranking
    ranking_data = api_client.get_ranking()
    if ranking_data is None:
        logger.error("Could not fetch news ranking. Skipping run.")
        return
    if not ranking_data:
        logger.info("No articles found in ranking. Skipping run.")
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
            # Continue even without body, maybe title translation is enough? Or skip?
            # Let's try translating title only if body is missing.

        # 5. Translate Title, Body and Generate Hashtags using OpenAI
        logger.info(f"--> Calling OpenAI translator for: {article_link}") # Log before call
        translation_result = await openai_translator.translate_and_summarize_article(
            title=original_title,
            body=original_body # Pass empty string if body wasn't found
        )
        logger.info(f"<-- Returned from OpenAI translator for: {article_link}. Result: {'Success' if translation_result else 'Failure'}") # Log after call

        if not translation_result:
            logger.error(f"Failed to get translation/hashtags from OpenAI for {article_link}. Skipping article.")
            continue # Skip this article if OpenAI call fails

        translated_title = translation_result.get('translated_title', '')
        translated_body = translation_result.get('translated_body', '')
        hashtags = translation_result.get('hashtags', [])

        if not translated_title: # Title is essential
             logger.error(f"OpenAI did not return a translated title for {article_link}. Skipping article.")
             continue

        # --- Check for Skip Keywords in Hashtags ---
        should_skip = False
        skip_keywords = config_manager.get("skip_keywords", []) # Get current skip keywords
        if skip_keywords:
            for tag in hashtags:
                tag_lower = tag.lower() # Case-insensitive check
                for keyword in skip_keywords:
                    if keyword in tag_lower:
                        logger.info(f"Skipping article '{original_title}' ({article_link}) due to keyword '{keyword}' found in hashtag '{tag}'.")
                        should_skip = True
                        break # Stop checking keywords for this tag
                if should_skip:
                    break # Stop checking tags for this article

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
                except ValueError:
                    logger.warning(f"Could not parse publication time: {publication_time_iso}")
                except Exception as time_e:
                     logger.error(f"Error formatting time '{publication_time_iso}': {time_e}")

            escaped_time = escape_markdown_v2(formatted_time_str)

            # Construct the message (adjust formatting as desired)
            message = f"*{escaped_title}*\n\n"
            if escaped_content:
                 message += f"{escaped_content}\n\n"
            message += f"[原文链接]({article_link})"
            if escaped_time:
                 message += f"\n_{escaped_time}_"

            # Add hashtags (escaped)
            if hashtags:
                valid_hashtags = [f"#{tag.lstrip('#')}" for tag in hashtags if isinstance(tag, str) and tag]
                if valid_hashtags:
                    escaped_hashtags = [escape_markdown_v2(tag) for tag in valid_hashtags]
                    message += "\n\n" + " ".join(escaped_hashtags)

        # 7. Post to Telegram (conditionally)
        message_id = None # Initialize message_id
        if not should_skip:
            if message: # Ensure message is not empty before posting
                logger.debug(f"Formatted message for {article_link}:\n{message}")
                message_id = await telegram_poster.post_message(message)
                if message_id is None:
                    logger.error(f"Failed to post article to Telegram (received None message_id): {article_link}")
            else:
                 logger.error(f"Message formatting resulted in empty message for {article_link}. Cannot post.")
        # If should_skip is True, message_id remains None

        # 8. Update posted articles file (always, regardless of skip status)
        # Note: message_id will be None if skipped or if posting failed
        data_handler.add_posted_article(
            filepath=config_manager.get("posted_articles_file"), # Get current path
            url=article_link,
            title=original_title, # Store original title for tracking
            message_id=message_id,
            skipped=should_skip # Pass the skip status
        )
        if not should_skip and message_id is not None:
             processed_count += 1 # Increment only if successfully posted

        # A small delay between processing articles
        await asyncio.sleep(5) # Sleep for 5 seconds

    logger.info(f"--- run_check function finished. Processed {processed_count} new articles. ---") # Log end of function


# --- Scheduler Integration ---
def run_scheduled_task():
    """Wrapper to run the async task using asyncio."""
    logger.info("Scheduler triggered run_check...")
    try:
        asyncio.run(run_check())
    except Exception as e:
        logger.exception("An error occurred during the scheduled task execution.")

# --- Main Execution ---
if __name__ == "__main__":
    # Get initial schedule interval
    schedule_interval = config_manager.get("schedule_interval_minutes")
    logger.info(f"Starting Yahoo News Bot. Initial check interval: {schedule_interval} minutes.")
    logger.info("Starting configuration file watcher...")
    config_manager.start_watching() # Start monitoring config.yaml

    # Run once immediately at startup
    logger.info("Running initial check...")
    run_scheduled_task()

    # Schedule the task using the initial interval
    # Note: Changes to schedule_interval_minutes in config.yaml will require a restart
    # to affect the schedule, as per the plan.
    logger.info(f"Scheduling checks every {schedule_interval} minutes.")
    schedule.every(schedule_interval).minutes.do(run_scheduled_task)

    # Keep the script running to allow the scheduler to work
    try:
        while True:
            schedule.run_pending()
            time.sleep(60) # Check every minute if jobs are due
    except KeyboardInterrupt:
        logger.info("Shutdown signal received (KeyboardInterrupt).")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main loop: {e}")
    finally:
        logger.info("Stopping configuration file watcher...")
        config_manager.stop_watching()
        logger.info("Yahoo News Bot shutting down.")