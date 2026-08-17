import re
from typing import Any

try:
    from langchain.agents.middleware import PIIMiddleware
except ImportError:  # Keeps local utilities usable before the full agent stack is installed.
    PIIMiddleware = None  # type: ignore[assignment]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+prompt",
    r"developer\s+message",
    r"reveal\s+(the\s+)?secret",
]

API_KEY_PATTERN = r"(sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*[:=]\s*[^\s,;]+|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*[:=]\s*[^\s,;]+|[Tt][Oo][Kk][Ee][Nn]\s*[:=]\s*[^\s,;]+)"
PRODUCT_INTERNAL_ID_PATTERN = r"\b(?:internal\s+sku|internal\s+part\s+number|erp\s+item|erp\s+id|vendor\s+item\s+id|supplier\s+sku|private\s+label\s+sku)\s*[:#=]?\s*[A-Za-z0-9][A-Za-z0-9._/-]{2,}\b"
PRODUCT_PRICING_PATTERN = r"\b(?:supplier\s+cost|landed\s+cost|unit\s+cost|contract\s+price|net\s+price|dealer\s+price|wholesale\s+price|margin|markup)\s*[:=]?\s*(?:[$€£₹]\s*)?\d+(?:[.,]\d{1,4})?\s*%?\b"
PRODUCT_CONFIDENTIAL_PATTERN = r"\b(?:confidential|proprietary|nda|do\s+not\s+distribute|not\s+for\s+public\s+release|pre[-\s]?release|unreleased\s+product|embargoed)\b"
PRODUCT_SERIAL_LICENSE_PATTERN = r"\b(?:serial\s+(?:number|no\.?)|license\s+(?:key|number)|activation\s+key|warranty\s+code)\s*[:#=]?\s*[A-Za-z0-9][A-Za-z0-9._/-]{5,}\b"

SENSITIVE_PRODUCT_PATTERNS = [
    PRODUCT_INTERNAL_ID_PATTERN,
    PRODUCT_PRICING_PATTERN,
    PRODUCT_CONFIDENTIAL_PATTERN,
    PRODUCT_SERIAL_LICENSE_PATTERN,
]


def sanitize_untrusted_text(text: str | None) -> str | None:
    if not text:
        return text
    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[removed instruction-like text]", sanitized, flags=re.I)
    return sanitized[:20_000]


def build_pii_middleware() -> list[Any]:
    """LangChain middleware used by the deepagents/LangGraph agent layer."""
    if PIIMiddleware is None:
        return []
    return [
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware("credit_card", strategy="mask", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware("ip", strategy="hash", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware("mac_address", strategy="hash", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware("api_key", detector=API_KEY_PATTERN, strategy="block", apply_to_input=True, apply_to_tool_results=True),
        PIIMiddleware(
            "product_internal_id",
            detector=PRODUCT_INTERNAL_ID_PATTERN,
            strategy="redact",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
        PIIMiddleware(
            "product_pricing",
            detector=PRODUCT_PRICING_PATTERN,
            strategy="redact",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
        PIIMiddleware(
            "product_confidential",
            detector=PRODUCT_CONFIDENTIAL_PATTERN,
            strategy="block",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
        PIIMiddleware(
            "product_serial_license",
            detector=PRODUCT_SERIAL_LICENSE_PATTERN,
            strategy="mask",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
    ]


def redact_for_non_agent_logs(value: Any) -> Any:
    """Fallback for data logged outside LangChain's agent middleware path."""
    if isinstance(value, str):
        redacted = re.sub(API_KEY_PATTERN, "[redacted]", value)
        for pattern in SENSITIVE_PRODUCT_PATTERNS:
            redacted = re.sub(pattern, "[redacted_product_sensitive]", redacted, flags=re.I)
        return redacted
    if isinstance(value, list):
        return [redact_for_non_agent_logs(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_for_non_agent_logs(item) for key, item in value.items()}
    return value
