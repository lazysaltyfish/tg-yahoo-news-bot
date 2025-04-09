import logging
import asyncio
import aiohttp
from urllib.parse import urljoin, urlencode
from .config import config_manager

logger = logging.getLogger(__name__)

# Note: aiohttp.ClientSession is typically created once and reused.
# For simplicity here, we create it per request in _make_request.
# Consider managing a single session instance in main.py for better performance.

async def _make_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict | None:
    """Helper function to make async API requests and handle common errors."""
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

    # Create a session for each request - less efficient but simpler for now
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        try:
            logger.debug(f"Making async {method} request to {full_url} with params={params}, json={json_data}")
            async with session.request(method, full_url, params=params, json=json_data) as response:
                # Check status code
                if response.status == 204: # No Content
                    logger.debug(f"Received 204 No Content from {full_url}")
                    return {} # Or None, depending on expected behavior

                # Raises ClientResponseError for bad responses (4xx or 5xx)
                response.raise_for_status()

                # Handle potential empty responses or non-JSON responses gracefully
                # Check content length header first if available
                if response.content_length == 0:
                     logger.warning(f"Received empty response body (Content-Length: 0) from {full_url}")
                     return None

                try:
                    # Use content_type='application/json' to avoid issues if server sends wrong type
                    json_response = await response.json(content_type=None)
                    if json_response is None: # Handle cases where response.json() returns None
                         logger.warning(f"Received null JSON response from {full_url}")
                         return None
                    return json_response
                except aiohttp.ContentTypeError:
                    # Log the actual content type and some text
                    response_text = await response.text()
                    logger.exception(f"Failed to decode JSON response from {full_url}. Content-Type: {response.content_type}. Response text: {response_text[:200]}...")
                    return None
                except Exception as json_e: # Catch potential json.JSONDecodeError etc.
                    response_text = await response.text()
                    logger.exception(f"Error decoding JSON from {full_url}: {json_e}. Response text: {response_text[:200]}...")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"Request timed out for {method} {full_url}")
            return None
        except aiohttp.ClientError as e: # Includes ClientConnectionError, ClientResponseError etc.
            logger.exception(f"aiohttp client error during {method} request to {full_url}: {e}")
            return None
        except Exception as e:
            logger.exception(f"An unexpected error occurred during async API request to {full_url}: {e}")
            return None


async def get_ranking() -> list:
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
    override_base = config_manager.get("yahoo_url_override_base") # Get override base once

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
            logger.debug(f"Replacing Yahoo JP prefix for ranking URL {i+1}. Original: {original_ranking_url}, New: {target_ranking_url}")
        else:
             logger.debug(f"No URL override applied for ranking URL: {original_ranking_url}")

        logger.debug(f"Fetching ranking from URL {i+1}/{len(ranking_urls)}: {target_ranking_url} (Original: {original_ranking_url})")
        params = {'url': target_ranking_url} # Pass the potentially modified ranking URL to the API
        response_data = await _make_request("GET", endpoint, params=params)

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
        logger.debug(f"Found {articles_found_this_url} new, valid articles from URL: {target_ranking_url} (Original: {original_ranking_url})")


    if not all_articles:
        logger.info("No valid, unique articles found across all configured ranking URLs.")
        return [] # Return empty list

    logger.info(f"Successfully fetched and combined {len(all_articles)} unique articles from {len(ranking_urls)} ranking URLs.")
    return all_articles


async def get_article_content(article_url: str) -> dict | None:
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
    override_base = config_manager.get("yahoo_url_override_base")
    if override_base and isinstance(override_base, str) and target_url.startswith(YAHOO_JP_PREFIX):
        # Ensure override_base ends with '/' if it doesn't already
        if not override_base.endswith('/'):
            override_base += '/'
        # Replace the prefix
        original_path = target_url[len(YAHOO_JP_PREFIX):]
        target_url = urljoin(override_base, original_path) # Use urljoin for safety
        logger.debug(f"Replacing Yahoo JP prefix. Original URL: {article_url}, New URL for API call: {target_url}")
    else:
        logger.debug(f"No URL override applied for: {article_url}")


    logger.debug(f"Fetching article content for: {target_url} (Original: {article_url})")
    endpoint = "/yahoo/article"
    params = {'url': target_url} # API takes URL as query param 'url'
    response_data = await _make_request("GET", endpoint, params=params)

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

    logger.debug(f"Successfully fetched and parsed content for article: {target_url} (Original: {article_url})")
    return article_data # Return the inner data dictionary