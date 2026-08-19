import logging
import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from product_agent.config import Settings, get_settings

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_QWEN_VL_MODEL = "Qwen/Qwen3-vl-4b"
DEFAULT_OLLAMA_MODEL = "ollama/qwen3-vl-4b"

try:
    import litellm
    # Prevent noisy litellm telemetry or stdout logs unless debugging
    litellm.suppress_debug_info = True
except ImportError:
    litellm = None  # type: ignore[assignment]


class LiteLLMGatewayChatModel(BaseChatModel):
    """Unified AI Gateway chat model powered by LiteLLM.

    Routes calls across multiple providers (Groq, Google Gemini, Ollama, HuggingFace)
    with automatic fallback and retries.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str = "groq/qwen3.6-27b"
    fallback_models: list[str] = Field(default_factory=list)
    api_key: str | None = None
    temperature: float = 0.1
    max_tokens: int = 2048
    bound_tools: Any = Field(default=None, exclude=True)
    tool_kwargs: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "litellm_gateway_chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model, "fallbacks": self.fallback_models}

    def bind_tools(self, tools: Any, **kwargs: Any) -> "LiteLLMGatewayChatModel":
        bound = self.model_copy()
        bound.bound_tools = tools
        bound.tool_kwargs = kwargs
        return bound

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if litellm is None:
            raise RuntimeError("Install `litellm` (`uv sync`) to use LiteLLMGatewayChatModel.")

        formatted_messages = [self._convert_message(m) for m in messages]
        candidates = [self.model, *[m for m in self.fallback_models if m != self.model]]

        last_error = None
        for candidate in candidates:
            try:
                logger.info("LiteLLM Gateway trying model candidate: %s", candidate)
                request: dict[str, Any] = {
                    "model": candidate,
                    "messages": formatted_messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                }
                if self.api_key:
                    request["api_key"] = self.api_key
                if self.bound_tools:
                    request["tools"] = self._format_tools_for_litellm(self.bound_tools)
                    request.update(self.tool_kwargs)
                if stop:
                    request["stop"] = stop
                request.update(kwargs)

                completion = litellm.completion(**request)
                choice = completion.choices[0]
                message = choice.message
                content = getattr(message, "content", "") or ""
                additional_kwargs: dict[str, Any] = {}
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    additional_kwargs["tool_calls"] = tool_calls

                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content=content, additional_kwargs=additional_kwargs))]
                )
            except Exception as exc:
                last_error = exc
                logger.warning("LiteLLM Gateway model '%s' failed: %s", candidate, exc)
                continue

        raise RuntimeError(f"All LiteLLM AI Gateway models failed ({candidates}). Last error: {last_error}")

    @staticmethod
    def _format_tools_for_litellm(tools: Any) -> Any:
        if not tools:
            return None
        try:
            from langchain_core.utils.function_calling import convert_to_openai_tool
            tool_list = tools if isinstance(tools, (list, tuple)) else [tools]
            formatted = []
            for t in tool_list:
                try:
                    formatted.append(convert_to_openai_tool(t))
                except Exception:
                    if hasattr(t, "model_json_schema"):
                        formatted.append({
                            "type": "function",
                            "function": {
                                "name": getattr(t, "__name__", "structured_output"),
                                "parameters": t.model_json_schema(),
                            }
                        })
                    elif hasattr(t, "schema"):
                        formatted.append({
                            "type": "function",
                            "function": {
                                "name": getattr(t, "__name__", "structured_output"),
                                "parameters": t.schema(),
                            }
                        })
                    else:
                        formatted.append(t)
            return formatted
        except Exception as exc:
            logger.debug("Tool formatting fallback: %s", exc)
            return tools

    @staticmethod
    def _convert_message(message: BaseMessage) -> dict[str, Any]:
        role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
        return {"role": role_map.get(message.type, message.type), "content": message.content}


def build_gateway_chat_model(settings: Settings | None = None) -> LiteLLMGatewayChatModel:
    """Build a LiteLLM AI Gateway chat model configured with primary and fallback providers."""
    settings = settings or get_settings()

    # Configure API keys into env if present in settings
    if settings.groq_api_key:
        os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)
    if settings.gemini_api_key:
        os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
        os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
    if settings.hf_token:
        os.environ.setdefault("HUGGINGFACE_API_KEY", settings.hf_token)

    # Determine candidates order based on available keys and settings
    fallbacks: list[str] = []

    # 1. Groq models
    if settings.groq_api_key or "GROQ_API_KEY" in os.environ:
        fallbacks.extend([settings.groq_model, "groq/qwen3.6-27b", "groq/openai-oss-120b"])

    # 2. Google Gemini models
    if settings.gemini_api_key or "GEMINI_API_KEY" in os.environ or "GOOGLE_API_KEY" in os.environ:
        fallbacks.extend([settings.gemini_model, "gemini/gemini-2.0-flash", "gemini/gemini-1.5-flash"])

    # 3. Local Ollama model
    ollama_tag = settings.ollama_model if settings.ollama_model.startswith("ollama/") else f"ollama/{settings.ollama_model}"
    fallbacks.append(ollama_tag)
    fallbacks.append("ollama/qwen3-vl-4b")

    # 4. HuggingFace models
    if settings.hf_token or "HUGGINGFACE_API_KEY" in os.environ:
        fallbacks.append(f"huggingface/{settings.hf_vlm_model}")

    # Remove duplicates preserving order
    deduped_candidates: list[str] = []
    for m in fallbacks:
        if m and m not in deduped_candidates:
            deduped_candidates.append(m)

    primary_model = settings.gateway_model or (deduped_candidates[0] if deduped_candidates else settings.groq_model)
    fallback_list = [m for m in deduped_candidates if m != primary_model]

    return LiteLLMGatewayChatModel(
        model=primary_model,
        fallback_models=fallback_list,
        temperature=settings.hf_temperature,
        max_tokens=settings.hf_max_new_tokens,
    )


# Backward compatibility helpers
try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None


def build_qwen_vl_chat_model(settings: Settings | None = None) -> Any:
    return build_gateway_chat_model(settings)


def build_ollama_qwen_model(settings: Settings | None = None) -> Any:
    return build_gateway_chat_model(settings)
