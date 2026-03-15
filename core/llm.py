import os
from functools import lru_cache

from core.config import get_settings


@lru_cache(maxsize=1)
def get_genai_client():
    from google import genai

    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


@lru_cache(maxsize=1)
def get_agent_model_name() -> str:
    settings = get_settings()
    # ADK agents can use a model string directly. Keep this centralized.
    return settings.google_model


def configure_runtime_environment() -> None:
    settings = get_settings()
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
