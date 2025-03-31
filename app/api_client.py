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


def get_ranking() -> list | None:
    """
    Fetches the current Yahoo News ranking.

    Returns:
        A list of article dictionaries (e.g., [{'url': '...', 'title': '...'}, ...])
        or None if an error occurs.
    """
    yahoo_ranking_url = config_manager.get("yahoo_ranking_base_url")
    if not yahoo_ranking_url:
        logger.error("YAHOO_RANKING_BASE_URL is not configured.")
        return None
    logger.info(f"Fetching Yahoo News ranking using base URL: {yahoo_ranking_url}...")
    endpoint = "/yahoo/ranking"
    params = {'url': yahoo_ranking_url} # Add ranking base url as parameter
    response_data = _make_request("GET", endpoint, params=params)

    if response_data is None:
        logger.error("Failed to fetch ranking data or received None.")
        return None

    # --- New Validation based on provided structure ---
    if not isinstance(response_data, dict):
        logger.error(f"Unexpected data type received from {endpoint}. Expected dict, got {type(response_data)}.")
        return None

    if response_data.get("status") != "success":
        logger.error(f"API request to {endpoint} was not successful. Status: {response_data.get('status')}. Message: {response_data.get('message', 'N/A')}")
        return None

    articles_list = response_data.get("data")
    if not isinstance(articles_list, list):
        logger.error(f"Expected 'data' field in response to be a list, but got {type(articles_list)}.")
        return None

    # Validate items within the list (checking for 'link' and 'title')
    valid_articles = []
    for item in articles_list:
        if isinstance(item, dict) and 'link' in item and 'title' in item:
            valid_articles.append(item)
        else:
            logger.warning(f"Skipping invalid article item in ranking response: {item}")

    if not valid_articles:
        logger.info("No valid articles found in the 'data' list of the ranking response.")
        # Return empty list instead of None if the API call was successful but data was empty/invalid
        return []

    logger.info(f"Successfully fetched and parsed {len(valid_articles)} articles from ranking.")
    return valid_articles


def get_article_content(article_url: str) -> dict | None:
    """
    Fetches the content of a specific Yahoo News article.
    The API is assumed to take the article URL as a query parameter.

    Args:
        article_url: The URL of the article to fetch.

    Returns:
        A dictionary containing the article details (e.g., {'title': '...', 'content': '...'})
        or None if an error occurs.
    """
    logger.info(f"Fetching article content for: {article_url}")
    endpoint = "/yahoo/article"
    params = {'url': article_url} # API takes URL as query param 'url'
    response_data = _make_request("GET", endpoint, params=params)

    if response_data is None:
        logger.error(f"Failed to fetch article content for {article_url} or received None.")
        return None

    # --- New Validation based on provided structure ---
    if not isinstance(response_data, dict):
        logger.error(f"Unexpected data type received from {endpoint} for {article_url}. Expected dict, got {type(response_data)}.")
        return None

    if response_data.get("status") != "success":
        logger.error(f"API request to {endpoint} for {article_url} was not successful. Status: {response_data.get('status')}. Message: {response_data.get('message', 'N/A')}")
        return None

    article_data = response_data.get("data")
    if not isinstance(article_data, dict):
        logger.error(f"Expected 'data' field in article response to be a dict, but got {type(article_data)} for {article_url}.")
        return None

    # Optional: Add checks for expected keys like 'title', 'body' within article_data if needed
    # if 'title' not in article_data or 'body' not in article_data:
    #     logger.warning(f"Article data for {article_url} might be missing expected keys ('title', 'body').")

    logger.info(f"Successfully fetched and parsed content for article: {article_url}")
    return article_data # Return the inner data dictionary