"""OpenAI-compatible LLM client with provider fallback and strict JSON validation."""
import json
import logging
import re
from typing import List, Optional, Tuple, Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from config import Settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def parse_json_object(text: str) -> Optional[dict]:
    """Parse the first JSON object in a model response (tolerates code fences / leading prose)."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._providers: List[Tuple[str, ChatOpenAI]] = []
        order = ["openrouter", "gemini"] if settings.llm_provider != "gemini" else ["gemini", "openrouter"]
        for name in order:
            client = self._build(name)
            if client:
                self._providers.append((name, client))

    def _build(self, name: str) -> Optional[ChatOpenAI]:
        s = self.settings
        if name == "openrouter" and s.openrouter_api_key:
            model, key, url = s.openrouter_model, s.openrouter_api_key, s.openrouter_base_url
        elif name == "gemini" and s.gemini_api_key:
            model, key, url = s.gemini_model, s.gemini_api_key, s.gemini_base_url
        else:
            return None
        return ChatOpenAI(
            model=model,
            api_key=key,
            base_url=url,
            temperature=s.llm_temperature,
            max_tokens=min(s.llm_max_tokens, 800),
            timeout=min(s.llm_timeout_s, 6.0) if s.demo_mode else s.llm_timeout_s,
            max_retries=0,
        )

    @property
    def available(self) -> bool:
        return bool(self._providers)

    @property
    def provider_names(self) -> List[str]:
        return [name for name, _ in self._providers]

    def structured(self, system: str, user: str, schema: Type[T]) -> Optional[T]:
        """Returns a validated schema instance, or None if every provider failed."""
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        for name, client in self._providers:
            try:
                response = client.invoke(messages, response_format={"type": "json_object"})
                data = parse_json_object(response.content if isinstance(response.content, str) else str(response.content))
                if data is None:
                    logger.warning("LLM %s returned non-JSON output", name)
                    continue
                return schema.model_validate(data)
            except ValidationError as exc:
                logger.warning("LLM %s output failed validation: %s", name, exc.errors()[:2])
            except Exception as exc:
                cause = exc.__cause__ or exc.__context__
                logger.warning("LLM %s call failed: %s (%s)", name, type(exc).__name__, type(cause).__name__ if cause else "-")
        return None
