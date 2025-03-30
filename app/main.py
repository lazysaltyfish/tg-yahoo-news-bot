import logging
import time
import schedule
import asyncio
import re
from app import config, logger_setup, api_client, data_handler, telegram_poster

# --- Setup ---
logger_setup.setup_logging()
logger = logging.getLogger(__name__)
config.log_config() # Log the loaded configuration

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
    posted_articles = data_handler.load_posted_articles(config.POSTED_ARTICLES_FILE)
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

        # --- Fetch and Translate Article Body ---
        content_to_translate = ""
        translated_content = ""
        content_data = api_client.get_article_content(article_link)
        if content_data and 'body' in content_data:
            body_text = content_data['body']
            if body_text and isinstance(body_text, str):
                 translated_content = api_client.translate_text(body_text)
                 if not translated_content:
                      logger.warning(f"Failed to translate body for {article_link}.")
                      translated_content = "" # Ensure it's an empty string if translation fails
            else:
                 logger.warning(f"Article body is empty or not a string for {article_link}.")
        else:
            logger.warning(f"Could not get body content for {article_link}. Skipping content translation.")


        # 5. Translate Title
        translated_title = api_client.translate_text(original_title)
        # Note: translated_content is handled above

        if not translated_title:
            logger.error(f"Failed to translate title for {article_link}. Skipping article.")
            continue # Skip this article if title translation fails

        # 6. Format Message
        # Escape necessary components for MarkdownV2
        escaped_title = escape_markdown_v2(translated_title)
        escaped_link = escape_markdown_v2(article_link)
        escaped_content = escape_markdown_v2(translated_content)
        publication_time = content_data.get('publication_time', '') if content_data else ''
        escaped_time = escape_markdown_v2(publication_time)

        # Construct the message (adjust formatting as desired)
        message = f"*{escaped_title}*\n\n"
        if escaped_content:
             # Add translated content summary if available
             message += f"{escaped_content}\n\n" # Add ellipsis
        message += f"[原文链接]({escaped_link})" # Link to original article using escaped_link
        if escaped_time:
             message += f"\n_{escaped_time}_" # Add escaped time on new line, italicized

        # 7. Post to Telegram
        logger.debug(f"Formatted message for {article_link}:\n{message}")
        success = await telegram_poster.post_message(message)

        # 8. Update posted articles file if successful
        if success:
            logger.info(f"Successfully posted article to Telegram: {article_link}")
            data_handler.add_posted_article(config.POSTED_ARTICLES_FILE, article_link, original_title)
            processed_count += 1
        else:
            logger.error(f"Failed to post article to Telegram: {article_link}")
            # Consider retry logic here? For now, we just log and move on.

        # Optional: Add a small delay between posts to avoid rate limiting
        await asyncio.sleep(2) # Sleep for 2 seconds

    logger.info(f"Finished news check run. Processed {processed_count} new articles.")


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
    logger.info(f"Starting Yahoo News Bot. Checks will run every {config.SCHEDULE_INTERVAL_MINUTES} minutes.")

    # Run once immediately at startup
    run_scheduled_task()

    # Schedule the task
    schedule.every(config.SCHEDULE_INTERVAL_MINUTES).minutes.do(run_scheduled_task)

    # Keep the script running to allow the scheduler to work
    while True:
        schedule.run_pending()
        time.sleep(60) # Check every minute if jobs are due