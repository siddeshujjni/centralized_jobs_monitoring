"""Foundation Model API client using OpenAI-compatible interface."""

import os
import logging
from openai import AsyncOpenAI
from server.config import get_oauth_token, get_workspace_host, IS_DATABRICKS_APP

logger = logging.getLogger(__name__)

# Default model - Claude Sonnet is great for structured analysis
DEFAULT_MODEL = os.environ.get("SERVING_ENDPOINT", "databricks-claude-sonnet-4-5")


def get_llm_client() -> AsyncOpenAI:
    """Get OpenAI-compatible client pointing at Databricks Foundation Model API."""
    host = get_workspace_host()
    token = get_oauth_token()

    return AsyncOpenAI(
        api_key=token,
        base_url=f"{host}/serving-endpoints",
    )


async def chat(system_prompt: str, user_message: str, model: str = DEFAULT_MODEL) -> str:
    """Send a chat message and return the text response."""
    client = get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=2048,
            temperature=0.3,  # Lower temp for factual analysis
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise
