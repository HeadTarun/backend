from functools import lru_cache
import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class Settings(BaseModel):
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_products_table: str = "products"
    hf_token: str | None = None
    hf_vlm_model: str = "Qwen/Qwen3-VL-4B-Instruct"
    enable_web_search: bool = False
    langsmith_tracing: bool = False
    langsmith_project: str = "industrial-commerce-product-agent"
    hf_max_new_tokens: int = 2048
    hf_temperature: float = 0.1


@lru_cache
def get_settings() -> Settings:
    return Settings(
        supabase_url=_env("SUPABASE_URL", "supabase_url"),
        supabase_key=_env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "supabase_service_key", "supabase_anon_key"),
        supabase_products_table=_env("SUPABASE_PRODUCTS_TABLE", "supabase_products_table", default="products") or "products",
        hf_token=os.getenv("HF_TOKEN"),
        hf_vlm_model=os.getenv("HF_VLM_MODEL", "Qwen/Qwen3-VL-4B-Instruct"),
        enable_web_search=os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true",
        langsmith_tracing=os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "industrial-commerce-product-agent"),
        hf_max_new_tokens=int(os.getenv("HF_MAX_NEW_TOKENS", "2048")),
        hf_temperature=float(os.getenv("HF_TEMPERATURE", "0.1")),
    )
