import os
from dataclasses import dataclass
from typing import Any

from product_agent.config import Settings, get_settings
from product_agent.llm import build_qwen_vl_chat_model
from product_agent.schemas import ProductInput, ProductIntelligence

try:
    from langchain.agents.middleware import AgentMiddleware
except ImportError:
    AgentMiddleware = object  # type: ignore[assignment,misc]

try:
    from deepagents.middleware.rubric import RubricMiddleware
except ImportError:
    RubricMiddleware = None  # type: ignore[assignment]

try:
    from langsmith import traceable
except ImportError:
    traceable = None  # type: ignore[assignment]


PRODUCT_INTELLIGENCE_RUBRICS = {
    "completeness": (
        "The output should include a commerce-ready title, category, description, "
        "features, specifications when available, applications, normalized attributes, "
        "source evidence, confidence, and quality warnings."
    ),
    "groundedness": (
        "Claims should be grounded in the input product identifiers, supporting text, "
        "provided URLs, retrieved similar products, or marked as inferred with warnings."
    ),
    "catalog_quality": (
        "The result should be suitable for industrial commerce: concise, normalized, "
        "buyer-oriented, unit-aware, and free of unsupported compatibility or certification claims."
    ),
    "traceability": (
        "The output should preserve source evidence and confidence indicators so a reviewer "
        "can understand why each product assertion was made."
    ),
    "spec_quality": (
        "Specifications should be normalized into name/value/unit fields where source text "
        "contains measurable ratings, dimensions, pressure, current, power, or voltage."
    ),
    "source_coverage": (
        "Each provided URL or supplied source text should be represented in the source "
        "evidence or reflected in quality warnings when scraping/evidence is unavailable."
    ),
    "sensitive_data": (
        "The output must not expose product-sensitive data such as internal SKUs, supplier "
        "costs, margins, contract prices, confidential launch details, serial numbers, "
        "license keys, or secrets."
    ),
}


@dataclass(frozen=True)
class RubricScore:
    key: str
    score: float
    comment: str


class ProductRubricMiddleware(AgentMiddleware):  # type: ignore[misc]
    """Fallback rubric middleware until LangChain's built-in RubricMiddleware is available."""

    def __init__(self, rubrics: dict[str, str]) -> None:
        super().__init__()
        self.rubrics = rubrics


def _traceable(name: str, run_type: str = "chain") -> Any:
    if traceable is None:
        def decorator(func: Any) -> Any:
            return func

        return decorator
    return traceable(
        name=name,
        project_name=get_settings().langsmith_project,
        metadata={"run_type": run_type},
    )


def configure_langsmith(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    if settings.langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project


def build_rubric_middleware(settings: Settings | None = None) -> list[Any]:
    """Build rubric middleware for `deepagents.create_deep_agent`.

    Deep Agents' RubricMiddleware is only active when the agent invocation
    state includes a `rubric` key. It should be passed to `create_deep_agent`,
    not applied to the deterministic FastAPI fallback orchestrator.
    """
    settings = settings or get_settings()
    configure_langsmith(settings)
    if RubricMiddleware is not None:
        return [
            RubricMiddleware(
                model=build_qwen_vl_chat_model(settings),
                max_iterations=2,
            )
        ]
    return [ProductRubricMiddleware(PRODUCT_INTELLIGENCE_RUBRICS)]


def product_intelligence_rubric() -> str:
    return "\n".join(f"- {name}: {criterion}" for name, criterion in PRODUCT_INTELLIGENCE_RUBRICS.items())


@_traceable(name="product_intelligence_evaluation", run_type="chain")
def evaluate_product_output(product_input: ProductInput, output: ProductIntelligence) -> list[RubricScore]:
    configure_langsmith()
    scores = [
        RubricScore("completeness", _score_completeness(output), "Checks required commerce fields and review metadata."),
        RubricScore("groundedness", _score_groundedness(product_input, output), "Checks that identifiers and evidence are preserved."),
        RubricScore("catalog_quality", _score_catalog_quality(output), "Checks buyer-facing copy and normalized attributes."),
        RubricScore("traceability", 1.0 if output.source_evidence else 0.0, "Requires at least one source evidence item."),
        RubricScore("spec_quality", _score_spec_quality(product_input, output), "Checks measurable specs are extracted and normalized."),
        RubricScore("source_coverage", _score_source_coverage(product_input, output), "Checks provided URLs/text are represented in evidence."),
        RubricScore("sensitive_data", _score_sensitive_data(output), "Flags obvious product-sensitive terms in generated output."),
    ]
    average = sum(score.score for score in scores) / len(scores)
    return [*scores, RubricScore("overall", average, "Average of deterministic rubric scores.")]


def _score_completeness(output: ProductIntelligence) -> float:
    checks = [
        bool(output.title),
        bool(output.category),
        bool(output.commerce_description),
        bool(output.key_features),
        bool(output.source_evidence),
        bool(output.confidence),
    ]
    return sum(checks) / len(checks)


def _score_groundedness(product_input: ProductInput, output: ProductIntelligence) -> float:
    checks = [
        output.manufacturer_part_number == product_input.manufacturer_part_number,
        output.brand.lower() == product_input.brand.lower(),
        bool(output.source_evidence),
        bool(output.quality_warnings) if not product_input.supporting_text and not product_input.supporting_urls else True,
    ]
    return sum(checks) / len(checks)


def _score_catalog_quality(output: ProductIntelligence) -> float:
    checks = [
        60 <= len(output.commerce_description) <= 600,
        bool(output.normalized_attributes) or bool(output.quality_warnings),
        not output.commerce_description.endswith("!"),
        output.category != "Unknown",
    ]
    return sum(checks) / len(checks)


def _score_spec_quality(product_input: ProductInput, output: ProductIntelligence) -> float:
    source_text = f"{product_input.short_description} {product_input.supporting_text or ''}"
    has_measurable_text = any(unit in source_text.lower() for unit in [" v", "vac", "vdc", " a", "ma", " w", "kw", "hp", "mm", "psi", "bar"])
    if not has_measurable_text:
        return 1.0 if output.quality_warnings or output.specifications else 0.75
    if not output.specifications:
        return 0.0
    checks = [
        all(spec.name and spec.value for spec in output.specifications),
        any(spec.unit for spec in output.specifications),
        bool(output.normalized_attributes),
    ]
    return sum(checks) / len(checks)


def _score_source_coverage(product_input: ProductInput, output: ProductIntelligence) -> float:
    expected_sources = len(product_input.supporting_urls) + (1 if product_input.supporting_text else 0)
    if expected_sources == 0:
        return 1.0 if output.quality_warnings else 0.5
    evidence_text = " ".join(f"{item.source_type} {item.locator} {item.excerpt}" for item in output.source_evidence).lower()
    covered_urls = sum(1 for url in product_input.supporting_urls if str(url).lower() in evidence_text)
    covered_text = 1 if product_input.supporting_text and output.source_evidence else 0
    return min((covered_urls + covered_text) / expected_sources, 1.0)


def _score_sensitive_data(output: ProductIntelligence) -> float:
    text = output.model_dump_json().lower()
    sensitive_terms = ["supplier cost", "contract price", "internal sku", "confidential", "license key", "serial number"]
    return 0.0 if any(term in text for term in sensitive_terms) else 1.0
