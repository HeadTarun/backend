from typing import Any

from deepagents import create_deep_agent

from product_agent.config import Settings, get_settings
from product_agent.evaluation import build_rubric_middleware, product_intelligence_rubric
from product_agent.guardrails import build_pii_middleware, sanitize_untrusted_text
from product_agent.llm import build_qwen_vl_chat_model
from product_agent.schemas import ProductInput
from product_agent.scraper import ProductPageScraper
from product_agent.storage import ProductStore
from product_agent.tools import AgentTools


SYSTEM_PROMPT = """You are an industrial commerce product intelligence agent.

Given limited product inputs, produce structured, commerce-ready product
intelligence. Ground claims in supplied text, supplied URLs, retrieved similar
products, or mark them as inferred. Preserve source evidence and confidence.
Never expose secrets, product-sensitive internal identifiers, confidential
launch details, supplier costs, contract prices, margins, serial numbers, or
license keys.
"""


def create_product_deep_agent(
    *,
    settings: Settings | None = None,
    store: ProductStore | None = None,
    tools: AgentTools | None = None,
    scraper: ProductPageScraper | None = None,
    model: Any | None = None,
) -> Any:
    settings = settings or get_settings()
    store = store or ProductStore(
        settings.supabase_url,
        settings.supabase_key,
        settings.supabase_products_table,
    )
    agent_tools = tools or AgentTools(store, scraper=scraper)

    def retrieve_similar_products(manufacturer_part_number: str, brand: str, short_description: str) -> str:
        """Retrieve validated products with the same MPN or similar descriptions from Supabase database."""
        product = ProductInput(
            manufacturer_part_number=manufacturer_part_number,
            brand=brand,
            short_description=short_description,
        )
        matches = agent_tools.retrieve_similar_products(product)
        return "\n".join(match.product.model_dump_json() for match in matches) or "No similar products found in database."

    def save_structured_output(payload_json: str) -> str:
        """Save a validated ProductIntelligence JSON payload to Supabase database."""
        from product_agent.schemas import ProductIntelligence

        product = ProductIntelligence.model_validate_json(payload_json)
        saved = agent_tools.save_structured_output(product)
        return saved.model_dump_json()

    def sanitize_source_text(text: str) -> str:
        """Sanitize untrusted scraped or uploaded product text before reasoning over it."""
        return sanitize_untrusted_text(text) or ""

    def scrape_product_url(url: str) -> str:
        """Render a product URL with Playwright browser and extract visible page content and specs."""
        return agent_tools.scrape_product_url(url)

    def search_web_tavily(query: str) -> str:
        """Search the web for industrial product specifications using custom query via Tavily API."""
        return agent_tools.tavily_search(query)

    def auto_search_and_scrape(manufacturer_part_number: str, brand: str, short_description: str) -> str:
        """Automatically search the web via Tavily and scrape product spec sheets using Playwright."""
        return agent_tools.auto_search_and_scrape(manufacturer_part_number, brand, short_description)

    return create_deep_agent(
        model=model or build_qwen_vl_chat_model(settings),
        system_prompt=SYSTEM_PROMPT,
        tools=[
            retrieve_similar_products,
            save_structured_output,
            sanitize_source_text,
            scrape_product_url,
            search_web_tavily,
            auto_search_and_scrape,
        ],
        middleware=[*build_pii_middleware(), *build_rubric_middleware(settings)],
    )



def deep_agent_input(product: ProductInput) -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Build product intelligence for this product:\n"
                    f"MPN: {product.manufacturer_part_number}\n"
                    f"Brand: {product.brand}\n"
                    f"Short description: {product.short_description}\n"
                    f"Supporting URLs: {[str(url) for url in product.supporting_urls]}\n"
                    f"Supporting text: {product.supporting_text or ''}"
                ),
            }
        ],
        "rubric": product_intelligence_rubric(),
    }
