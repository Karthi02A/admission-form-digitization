"""Environment-driven AI provider settings for the shared extraction pipeline."""
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

_backend_env = Path(__file__).resolve().parents[2] / ".env"
_project_env = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_backend_env)
if _project_env != _backend_env:
    load_dotenv(_project_env)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


@dataclass(frozen=True)
class AISettings:
    provider: str
    api_key: str
    model: str
    base_url: str
    request_timeout_seconds: int
    max_retries: int
    max_concurrent_requests: int


def load_ai_settings() -> AISettings:
    """Resolve provider credentials. Shared extraction logic is provider-agnostic.

    Supported native adapters: Gemini, OpenAI Responses API, Anthropic Claude,
    and Mistral. OpenRouter and custom OpenAI-compatible chat-completions APIs
    use the compatible adapter. A provider must expose the documented API format.
    """
    provider = os.getenv("AI_PROVIDER", os.getenv("EXTRACTION_PROVIDER", "gemini")).strip().lower()
    aliases = {
        "anthropic": "claude", "claude": "claude",
        "openai-compatible": "openai_compatible",
        "openai-compatible-api": "openai_compatible",
        "openai_compatible": "openai_compatible",
    }
    provider = aliases.get(provider, provider)

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", os.getenv("AI_API_KEY", "")).strip()
        model = os.getenv("GEMINI_MODEL", os.getenv("AI_MODEL", "gemini-3.1-flash-lite")).strip()
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", os.getenv("AI_API_KEY", "")).strip()
        model = os.getenv("OPENAI_MODEL", os.getenv("AI_MODEL", "")).strip()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    elif provider == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY", os.getenv("CLAUDE_API_KEY", os.getenv("AI_API_KEY", ""))).strip()
        model = os.getenv("CLAUDE_MODEL", os.getenv("ANTHROPIC_MODEL", os.getenv("AI_MODEL", ""))).strip()
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").strip().rstrip("/")
    elif provider == "mistral":
        api_key = os.getenv("MISTRAL_API_KEY", os.getenv("AI_API_KEY", "")).strip()
        model = os.getenv("MISTRAL_MODEL", os.getenv("AI_MODEL", "mistral-small-latest")).strip()
        base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").strip().rstrip("/")
    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", os.getenv("AI_API_KEY", "")).strip()
        model = os.getenv("OPENROUTER_MODEL", os.getenv("AI_MODEL", "")).strip()
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
    elif provider == "openai_compatible":
        api_key = os.getenv("AI_API_KEY", "").strip()
        model = os.getenv("AI_MODEL", "").strip()
        base_url = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise ValueError("AI_BASE_URL is required when AI_PROVIDER=openai_compatible.")
    else:
        raise ValueError("AI_PROVIDER must be one of: gemini, openai, claude, mistral, openrouter, openai_compatible.")

    if not model:
        raise ValueError(f"Configure the model name for AI_PROVIDER='{provider}'.")
    if not base_url:
        raise ValueError("The provider base URL cannot be empty.")

    return AISettings(
        provider=provider, api_key=api_key, model=model, base_url=base_url,
        request_timeout_seconds=_positive_int("AI_REQUEST_TIMEOUT_SECONDS", 120),
        max_retries=_nonnegative_int("AI_MAX_RETRIES", 1),
        max_concurrent_requests=_positive_int("AI_MAX_CONCURRENT_REQUESTS", 2),
    )
