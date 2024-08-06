import aiohttp

from aijson.models.config.model import ModelType
from aijson.utils.secret_utils import get_secret


async def infer_default_llm() -> ModelType | None:
    # OpenAI
    if get_secret("OPENAI_API_KEY"):
        return "gpt-4o"

    # Anthropic
    if get_secret("ANTHROPIC_API_KEY"):
        return "claude-3-5-sonnet-20240620"

    # Ollama
    ollama_url = "http://localhost:11434/api/tags"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ollama_url) as response:
                data = await response.json()
                return f'ollama/{data["models"][0]["name"]}'
    except Exception:
        pass

    return None
