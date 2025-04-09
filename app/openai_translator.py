import logging
import json
from openai import AsyncOpenAI, OpenAIError # Use AsyncOpenAI for async operations
from .config import config_manager

logger = logging.getLogger(__name__)

# --- OpenAI Client Initialization (Removed) ---
# Client will be initialized dynamically within the function call
# to ensure latest configuration is used.

# --- Prompt Definition ---
# Define the prompt directly in the code as requested
TRANSLATION_SYSTEM_PROMPT = """
You are a helpful assistant tasked with translating Japanese news articles into Chinese
and generating relevant hashtags.

Input will be a Japanese title and body.
Output MUST be a single JSON object containing the following keys:
- "translated_title": The Chinese translation of the original title.
- "translated_body": The Chinese translation of the original body. Keep the translation concise but informative. 请使用合理的段落格式（可以考虑和原文段落一致）,注意分段的时候使用两个换行符,使得生成的文本有更好的人类可读性,而不是完全一整段很长的文本.
- "hashtags": A JSON array of 2-6 relevant Chinese hashtags (strings starting with '#').

Example Input:
###Title###: 速報：東京で大地震発生、被害状況確認中
###Body###: 本日午後3時頃、東京地方を震源とする強い地震が発生しました。気象庁によると、マグニチュードは7.0と推定されています。現在、被害状況の確認が進められています。交通機関にも影響が出ています。

Example Output JSON:
{
  "translated_title": "快讯：东京发生大地震，受灾情况确认中",
  "translated_body": "今日下午3时左右，东京地区发生强烈地震，震源位于该地。据气象厅消息，震级推测为7.0级。目前正在确认受灾情况。交通系统也受到了影响。",
  "hashtags": ["#东京地震", "#日本新闻", "#自然灾害", "#紧急速报"]
}

Ensure the output is ONLY the JSON object and nothing else. Note that the markdown style json is NOT allowed.
"""

async def translate_and_summarize_article(title: str, body: str) -> dict | None:
    """
    Translates article title and body to Chinese and generates hashtags using OpenAI.

    Args:
        title: The original Japanese article title.
        body: The original Japanese article body.

    Returns:
        A dictionary with 'translated_title', 'translated_body', and 'hashtags'
        if successful, None otherwise.
    """
    # --- Fetch Config and Initialize Client ---
    api_key = config_manager.get("openai_api_key")
    base_url = config_manager.get("openai_api_base_url") # Can be None
    model = config_manager.get("openai_model")
    temperature = config_manager.get("openai_temperature")
    max_tokens = config_manager.get("openai_max_tokens")

    if not api_key:
        logger.error("OpenAI API Key is not configured. Cannot perform translation.")
        return None
    if not model:
         logger.error("OpenAI Model is not configured. Cannot perform translation.")
         return None

    client = None # Initialize client to None
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.debug(f"OpenAI client CREATED for request (Title: {title[:20]}...). Instance ID: {id(client)}") # Log creation
    except OpenAIError as e:
        logger.exception(f"Failed to initialize OpenAI client for request: {e}")
        return None
    # Note: No explicit client.aclose() here

    if not title and not body:
        logger.warning("translate_and_summarize_article called with empty title and body.")
        # Return a structure indicating no translation needed or possible?
        # For now, return None as it's likely an issue upstream.
        return None

    # Construct the user message content for the API call
    user_content = f"###Title###: {title}\n###Body###: {body}"

    logger.debug(f"Sending request to OpenAI for title: {title[:50]}...")
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            # Request JSON response format if supported by the model/API version
            # Note: This might require specific model versions (e.g., gpt-4-1106-preview)
            response_format={"type": "json_object"} # Enforce JSON output mode
        )

        # Extract the response content
        response_content = response.choices[0].message.content
        if not response_content:
            logger.error("OpenAI response content is empty.")
            return None

        logger.debug(f"Raw OpenAI response: {response_content[:200]}...") # Log snippet

        # Parse the JSON response
        try:
            # The response might contain markdown ```json ... ```, try to extract JSON part
            json_str = response_content.strip()
            if json_str.startswith("```json"):
                # Find the first '{' and the last '}' to extract the JSON object
                start_index = json_str.find('{')
                end_index = json_str.rfind('}')
                if start_index != -1 and end_index != -1 and start_index < end_index:
                    json_str = json_str[start_index:end_index+1]
                else:
                    logger.error(f"Could not extract JSON object from markdown block: {response_content[:200]}...")
                    return None
            elif not json_str.startswith("{"):
                 logger.error(f"OpenAI response does not appear to be JSON: {response_content[:200]}...")
                 return None

            result_data = json.loads(json_str)

            # Validate the structure of the parsed JSON
            if not isinstance(result_data, dict) or \
               'translated_title' not in result_data or \
               'translated_body' not in result_data or \
               'hashtags' not in result_data or \
               not isinstance(result_data['hashtags'], list):
                logger.error(f"Invalid JSON structure received from OpenAI: {result_data}")
                return None

            logger.debug(f"OpenAI function EXITING NORMALLY (Title: {title[:20]}...). Instance ID: {id(client)}") # Log normal exit
            logger.info(f"Successfully translated and generated hashtags for title: {title[:50]}...")
            return result_data

        except json.JSONDecodeError:
            logger.exception(f"Failed to decode JSON response from OpenAI. Response: {response_content[:500]}")
            logger.debug(f"OpenAI function EXITING AFTER JSON ERROR (Title: {title[:20]}...). Instance ID: {id(client)}") # Log exit
            return None
        except Exception as e: # Catch other potential parsing errors
             logger.exception(f"Error processing OpenAI JSON response: {e}. Response: {response_content[:500]}")
             logger.debug(f"OpenAI function EXITING AFTER OTHER PARSE ERROR (Title: {title[:20]}...). Instance ID: {id(client)}") # Log exit
             return None

    except OpenAIError as e:
        logger.exception(f"OpenAI API error during translation: {e}")
        logger.debug(f"OpenAI function EXITING AFTER API ERROR (Title: {title[:20]}...). Instance ID: {id(client)}") # Log exit
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during OpenAI call: {e}")
        logger.debug(f"OpenAI function EXITING AFTER UNEXPECTED ERROR (Title: {title[:20]}...). Instance ID: {id(client)}") # Log exit
        return None