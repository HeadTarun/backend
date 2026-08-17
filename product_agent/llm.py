from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from product_agent.config import Settings, get_settings
from dotenv import load_dotenv
load_dotenv()

DEFAULT_QWEN3_VL_MODEL = "Qwen/Qwen3-VL-4B-Instruct"

try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None  # type: ignore[assignment]


class HuggingFaceQwenVLChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    api_key: str
    max_new_tokens: int = 2048
    temperature: float = 0.1
    client: Any = Field(default=None, exclude=True)
    bound_tools: Any = Field(default=None, exclude=True)
    tool_kwargs: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if InferenceClient is None:
            raise RuntimeError("Install `huggingface-hub` with `uv sync` before creating the Qwen Hugging Face model.")
        self.client = InferenceClient(api_key=self.api_key)

    @property
    def _llm_type(self) -> str:
        return "huggingface_qwen_vl_chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model}

    def bind_tools(self, tools: Any, **kwargs: Any) -> "HuggingFaceQwenVLChatModel":
        bound = self.model_copy()
        bound.client = self.client
        bound.bound_tools = tools
        bound.tool_kwargs = kwargs
        return bound

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [self._convert_message(message) for message in messages],
            "max_tokens": self.max_new_tokens,
            "temperature": self.temperature,
        }
        if self.bound_tools:
            request["tools"] = self.bound_tools
            request.update(self.tool_kwargs)
        if stop:
            request["stop"] = stop
        request.update(kwargs)

        completion = self.client.chat.completions.create(**request)
        message = completion.choices[0].message
        content = getattr(message, "content", "") or ""
        additional_kwargs: dict[str, Any] = {}
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            additional_kwargs["tool_calls"] = tool_calls
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content, additional_kwargs=additional_kwargs))])

    @staticmethod
    def _convert_message(message: BaseMessage) -> dict[str, Any]:
        role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
        return {"role": role_map.get(message.type, message.type), "content": message.content}


def build_qwen_vl_chat_model(settings: Settings | None = None) -> HuggingFaceQwenVLChatModel:
    settings = settings or get_settings()
    if not settings.hf_token:
        raise RuntimeError("Set HF_TOKEN in your environment or .env file before creating the Qwen Hugging Face model.")
    return HuggingFaceQwenVLChatModel(
        model=settings.hf_vlm_model or DEFAULT_QWEN3_VL_MODEL,
        api_key=settings.hf_token,
        max_new_tokens=settings.hf_max_new_tokens,
        temperature=settings.hf_temperature,
    )
