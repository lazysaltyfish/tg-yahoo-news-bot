import logging
import requests
from urllib.parse import urljoin, urlencode
from .config import config_manager

logger = logging.getLogger(__name__)

# Use a session object for potential connection reuse and default headers
session = requests.Session()
# You could add default headers here if needed, e.g.:
# session.headers.update({'User-Agent': 'YahooNewsTelegramBot/1.0'})

def _make_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict | None:
    """Helper function to make API requests and handle common errors."""
    # Construct URL manually to avoid urljoin issues with base path
    base_url = config_manager.get("api_base_url")
    if not base_url: # Check if base_url is None or empty
        logger.error("API_BASE_URL is not configured.")
        return None
    if not base_url.endswith('/'):
        base_url += '/'
    # Ensure endpoint doesn't start with '/' if base already ends with '/'
    relative_endpoint = endpoint.lstrip('/')
    full_url = urljoin(base_url, relative_endpoint)

    try:
        logger.debug(f"Making {method} request to {full_url} with params={params}, json={json_data}")
        response = session.request(method, full_url, params=params, json=json_data, timeout=30) # 30-second timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

        # Handle potential empty responses or non-JSON responses gracefully
        if response.status_code == 204: # No Content
             logger.info(f"Received 204 No Content from {full_url}")
             return {} # Or None, depending on expected behavior
        if not response.content:
             logger.warning(f"Received empty response body from {full_url}")
             return None

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            logger.exception(f"Failed to decode JSON response from {full_url}. Response text: {response.text[:200]}...") # Log snippet
            return None

    except requests.exceptions.Timeout:
        logger.error(f"Request timed out for {method} {full_url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error during {method} request to {full_url}: {e}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during API request to {full_url}: {e}")
        return None


def get_ranking() -> list:
    """
    Fetches Yahoo News ranking from multiple configured URLs, combines, and deduplicates.

    Returns:
        A list of unique article dictionaries (e.g., [{'link': '...', 'title': '...'}, ...]).
        Returns an empty list if no URLs are configured or no valid articles are found.
    """
    ranking_urls = config_manager.get("yahoo_ranking_base_urls", [])
    if not ranking_urls:
        logger.warning("YAHOO_RANKING_BASE_URLS is not configured or is empty. Cannot fetch rankings.")
        return []

    logger.info(f"Fetching Yahoo News rankings from {len(ranking_urls)} URLs...")
    endpoint = "/yahoo/ranking"
    all_articles = []
    seen_article_links = set()

    YAHOO_JP_PREFIX = "https://news.yahoo.co.jp/"
    override_base = config_manager.get("yahoo_article_url_override_base") # Get override base once

    for i, original_ranking_url in enumerate(ranking_urls):
        target_ranking_url = original_ranking_url # URL to be potentially modified

        # Check for URL override
        if override_base and isinstance(override_base, str) and target_ranking_url.startswith(YAHOO_JP_PREFIX):
            # Ensure override_base ends with '/' if it doesn't already
            if not override_base.endswith('/'):
                override_base += '/'
            # Replace the prefix
            original_path = target_ranking_url[len(YAHOO_JP_PREFIX):]
            target_ranking_url = urljoin(override_base, original_path) # Use urljoin for safety
            logger.info(f"Replacing Yahoo JP prefix for ranking URL {i+1}. Original: {original_ranking_url}, New: {target_ranking_url}")
        else:
             logger.debug(f"No URL override applied for ranking URL: {original_ranking_url}")

        logger.info(f"Fetching ranking from URL {i+1}/{len(ranking_urls)}: {target_ranking_url} (Original: {original_ranking_url})")
        params = {'url': target_ranking_url} # Pass the potentially modified ranking URL to the API
        response_data = _make_request("GET", endpoint, params=params)

        if response_data is None:
            logger.error(f"Failed to fetch ranking data or received None for URL: {target_ranking_url} (Original: {original_ranking_url})")
            continue # Skip to the next URL

        # --- Validation for the response from this specific URL ---
        if not isinstance(response_data, dict):
            logger.error(f"Unexpected data type received from {endpoint} for URL {target_ranking_url} (Original: {original_ranking_url}). Expected dict, got {type(response_data)}.")
            continue

        if response_data.get("status") != "success":
            logger.error(f"API request to {endpoint} for URL {target_ranking_url} (Original: {original_ranking_url}) was not successful. Status: {response_data.get('status')}. Message: {response_data.get('message', 'N/A')}")
            continue

        articles_list = response_data.get("data")
        if not isinstance(articles_list, list):
            logger.error(f"Expected 'data' field in response for URL {target_ranking_url} (Original: {original_ranking_url}) to be a list, but got {type(articles_list)}.")
            continue

        # Validate items within the list and deduplicate
        articles_found_this_url = 0
        for item in articles_list:
            if isinstance(item, dict) and 'link' in item and 'title' in item:
                article_link = item.get('link')
                if article_link and article_link not in seen_article_links:
                    seen_article_links.add(article_link)
                    all_articles.append(item)
                    articles_found_this_url += 1
                # else: logger.debug(f"Duplicate article skipped: {article_link}") # Optional: log duplicates
            else:
                logger.warning(f"Skipping invalid article item in ranking response from {target_ranking_url} (Original: {original_ranking_url}): {item}")
        logger.info(f"Found {articles_found_this_url} new, valid articles from URL: {target_ranking_url} (Original: {original_ranking_url})")


    if not all_articles:
        logger.info("No valid, unique articles found across all configured ranking URLs.")
        return [] # Return empty list

    logger.info(f"Successfully fetched and combined {len(all_articles)} unique articles from {len(ranking_urls)} ranking URLs.")
    return all_articles


def get_article_content(article_url: str) -> dict | None:
    """
    Fetches the content of a specific Yahoo News article.
    Optionally replaces the base URL if configured.
    The API is assumed to take the article URL as a query parameter.

    Args:
        article_url: The URL of the article to fetch.

    Returns:
        A dictionary containing the article details (e.g., {'title': '...', 'content': '...'})
        or None if an error occurs.
    """
    YAHOO_JP_PREFIX = "https://news.yahoo.co.jp/"
    target_url = article_url # Use a new variable for the potentially modified URL

    # Check for URL override
    override_base = config_manager.get("yahoo_article_url_override_base")
    if override_base and isinstance(override_base, str) and target_url.startswith(YAHOO_JP_PREFIX):
        # Ensure override_base ends with '/' if it doesn't already
        if not override_base.endswith('/'):
            override_base += '/'
        # Replace the prefix
        original_path = target_url[len(YAHOO_JP_PREFIX):]
        target_url = urljoin(override_base, original_path) # Use urljoin for safety
        logger.info(f"Replacing Yahoo JP prefix. Original URL: {article_url}, New URL for API call: {target_url}")
    else:
        logger.debug(f"No URL override applied for: {article_url}")


    logger.info(f"Fetching article content for: {target_url} (Original: {article_url})")
    endpoint = "/yahoo/article"
    params = {'url': target_url} # API takes URL as query param 'url'
    response_data = _make_request("GET", endpoint, params=params)

    if response_data is None:
        logger.error(f"Failed to fetch article content for {target_url} (Original: {article_url}) or received None.")
        return None

    # --- New Validation based on provided structure ---
    if not isinstance(response_data, dict):
        logger.error(f"Unexpected data type received from {endpoint} for {target_url} (Original: {article_url}). Expected dict, got {type(response_data)}.")
        return None

    if response_data.get("status") != "success":
        logger.error(f"API request to {endpoint} for {target_url} (Original: {article_url}) was not successful. Status: {response_data.get('status')}. Message: {response_data.get('message', 'N/A')}")
        return None

    article_data = response_data.get("data")
    if not isinstance(article_data, dict):
        logger.error(f"Expected 'data' field in article response to be a dict, but got {type(article_data)} for {target_url} (Original: {article_url}).")
        return None

    # Optional: Add checks for expected keys like 'title', 'body' within article_data if needed
    # if 'title' not in article_data or 'body' not in article_data:
    #     logger.warning(f"Article data for {target_url} (Original: {article_url}) might be missing expected keys ('title', 'body').")

    logger.info(f"Successfully fetched and parsed content for article: {target_url} (Original: {article_url})")
    return article_data # Return the inner data dictionary