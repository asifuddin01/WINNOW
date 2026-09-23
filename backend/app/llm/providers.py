"""The configured AI provider (guide 8.11, 16.1: LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL,
LLM_MODEL). Set up by the instance's administrator in the environment; nothing here is
stored in the database, and nothing is sent anywhere unless a review's owner opts in.

- `anthropic`: Claude, through the official SDK, with structured output and the API's
  refusal fallbacks.
- `openai_compatible`: a local or self-hosted model behind an OpenAI-style
  `/chat/completions` endpoint, such as Ollama.
"""

from typing import Any, Protocol

import anthropic
import httpx

from app.config import Settings

ANTHROPIC_MODEL = "claude-opus-5"
# Models that take the API's server-side refusal fallback ("default" routes a declined
# request to Anthropic's recommended model for the reason it was declined).
FALLBACK_MODELS = frozenset({"claude-opus-5", "claude-fable-5", "claude-fable-5-1"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
TIMEOUT_SECONDS = 60.0
MAX_TOKENS = 16_000


class ProviderError(Exception):
    """The provider could not give a suggestion; the message is safe to show."""


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """The provider's answer: JSON text in the shape of `schema`."""
        ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        *,
        http_client: anthropic.DefaultAsyncHttpxClient | None = None,
        max_retries: int = 2,
    ) -> None:
        self.model = model or ANTHROPIC_MODEL
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=TIMEOUT_SECONDS,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def complete(self, system: str, user: str, schema: dict[str, Any]) -> str:
        extra: dict[str, Any] = {}
        if self.model in FALLBACK_MODELS:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                # A short judgement against written criteria: low effort keeps a reviewer
                # waiting seconds, not tens of seconds.
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": schema},
                },
                **extra,
            )
        except anthropic.RateLimitError as error:
            raise ProviderError("The AI provider is busy. Try again in a minute.") from error
        except anthropic.AuthenticationError as error:
            raise ProviderError("The AI provider refused this instance's API key.") from error
        except anthropic.APIStatusError as error:
            raise ProviderError(f"The AI provider answered {error.status_code}.") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError("The AI provider could not be reached.") from error
        if response.stop_reason == "refusal":
            raise ProviderError("The AI provider declined to assess this record.")
        if response.stop_reason == "max_tokens":
            raise ProviderError("The AI provider's answer was cut off.")
        for block in response.content:
            if block.type == "text":
                text: str = block.text
                return text
        raise ProviderError("The AI provider gave no answer.")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, http: httpx.AsyncClient, base_url: str, model: str, api_key: str | None):
        self.model = model
        self._http = http
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def complete(self, system: str, user: str, schema: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "screening_suggestion", "schema": schema, "strict": True},
            },
            "temperature": 0,
        }
        try:
            response = await self._http.post(
                self._url, json=body, headers=self._headers, timeout=TIMEOUT_SECONDS
            )
        except httpx.HTTPError as error:
            raise ProviderError("The AI provider could not be reached.") from error
        if response.status_code != 200:
            raise ProviderError(f"The AI provider answered {response.status_code}.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderError("The AI provider's answer could not be read.") from error
        if not isinstance(content, str):
            raise ProviderError("The AI provider gave no answer.")
        return content


def is_configured(settings: Settings) -> bool:
    """Whether the environment names a provider with what it needs to be called."""
    if settings.llm_provider == "anthropic":
        return settings.llm_api_key is not None
    if settings.llm_provider == "openai_compatible":
        return settings.llm_base_url is not None and bool(settings.llm_model)
    return False


def create_provider(settings: Settings, http: httpx.AsyncClient) -> Provider | None:
    """The provider this instance is set up for, or None when AI suggestions are off."""
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    if not is_configured(settings):
        return None
    if settings.llm_provider == "anthropic" and key:
        return AnthropicProvider(key, settings.llm_model)
    return OpenAICompatibleProvider(http, str(settings.llm_base_url), settings.llm_model or "", key)
