from functools import lru_cache
import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            clean = value.strip().strip("'\"")
            if clean:
                return clean
    return default


class Settings(BaseModel):
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_products_table: str = "rag_products"
    hf_token: str | None = None
    hf_vlm_model: str = "Qwen/Qwen2.5-72B-Instruct"
    groq_api_key: str | None = None
    groq_model: str = "groq/qwen3.6-27b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini/gemini-2.0-flash"
    ollama_model: str = "ollama/qwen3-vl-4b"
    gateway_model: str | None = None
    tavily_api_key: str | None = None
    tavily_max_results: int = 5
    enable_web_search: bool = False
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = True
    langsmith_project: str = "industrial-commerce-product-agent"
    hf_max_new_tokens: int = 2048
    hf_temperature: float = 0.1


@lru_cache
def get_settings() -> Settings:
    tbl = _env("SUPABASE_PRODUCTS_TABLE", "supabase_products_table", default="rag_products") or "rag_products"
    l_key = _env("LANGSMITH_API_KEY", "langsmith_api_key")
    l_tracing_str = _env("LANGSMITH_TRACING", "langsmith_tracing")
    l_tracing = (l_tracing_str.lower() == "true") if l_tracing_str else bool(l_key)
    return Settings(
        supabase_url=_env("SUPABASE_URL", "supabase_url"),
        supabase_key=_env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "supabase_service_key", "supabase_anon_key"),
        supabase_products_table=tbl,
        hf_token=_env("HF_TOKEN"),
        hf_vlm_model=_env("HF_VLM_MODEL", default="Qwen/Qwen2.5-72B-Instruct") or "Qwen/Qwen2.5-72B-Instruct",
        groq_api_key=_env("GROQ_API_KEY", "groq_api_key"),
        groq_model=_env("GROQ_MODEL", "groq_model", default="groq/qwen3.6-27b") or "groq/qwen3.6-27b",
        gemini_api_key=_env("GEMINI_API_KEY", "gemini_api_key", "GOOGLE_API_KEY", "google_api_key"),
        gemini_model=_env("GEMINI_MODEL", "gemini_model", default="gemini/gemini-2.0-flash") or "gemini/gemini-2.0-flash",
        ollama_model=_env("OLLAMA_MODEL", "ollama_model", default="ollama/qwen3-vl-4b") or "ollama/qwen3-vl-4b",
        gateway_model=_env("GATEWAY_MODEL", "gateway_model"),
        tavily_api_key=_env("TAVILY_API_KEY", "tavily_api_key", "TAVILY_API", "tavily_api"),
        tavily_max_results=int(_env("TAVILY_MAX_RESULTS", default="5") or "5"),
        enable_web_search=bool(_env("TAVILY_API_KEY", "tavily_api_key", "TAVILY_API", "tavily_api")),
        langsmith_api_key=l_key,
        langsmith_tracing=l_tracing,
        langsmith_project=_env("LANGSMITH_PROJECT", default="industrial-commerce-product-agent") or "industrial-commerce-product-agent",
        hf_max_new_tokens=int(_env("HF_MAX_NEW_TOKENS", default="2048") or "2048"),
        hf_temperature=float(_env("HF_TEMPERATURE", default="0.1") or "0.1"),
    )

