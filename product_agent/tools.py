import logging
from typing import Any

from product_agent.guardrails import sanitize_untrusted_text
from product_agent.schemas import ProductInput, ProductIntelligence, RetrievalMatch
from product_agent.scraper import ProductPageScraper
from product_agent.storage import ProductStore
from product_agent.web_search import ProductWebSearcher

logger = logging.getLogger(__name__)


class AgentTools:
    """Tool execution harness for the Product Intelligence Agent.

    Exposes storage retrieval, web scraping, Tavily search, and sanitization
    utilities that can be called directly or registered as LLM agent tools.
    """

    def __init__(
        self,
        store: ProductStore,
        scraper: ProductPageScraper | None = None,
        searcher: ProductWebSearcher | None = None,
    ) -> None:
        self.store = store
        self.scraper = scraper or ProductPageScraper()
        self.searcher = searcher

    def retrieve_similar_products(self, product: ProductInput, limit: int = 5) -> list[RetrievalMatch]:
        """Retrieve validated products with exact MPN match or semantic keyword overlap."""
        exact = self.store.exact_match(product.manufacturer_part_number, product.brand)
        if exact:
            return [RetrievalMatch(score=1.0, match_type="exact_mpn", product=exact)]
        query = f"{product.brand} {product.manufacturer_part_number} {product.short_description}"
        return self.store.search(query, limit=limit)

    def save_structured_output(self, product: ProductIntelligence) -> ProductIntelligence:
        """Persist structured ProductIntelligence object into Supabase database."""
        return self.store.save(product)

    def parse_doc_or_image(self, text_or_path: str | None) -> str | None:
        """Parse industrial document or sanitize raw text using LlamaCloud Document Intelligence."""
        if not text_or_path:
            return None
        # If input looks like a document filepath or URL, run LlamaCloud
        if text_or_path.endswith((".pdf", ".docx", ".pptx", ".txt")) or text_or_path.startswith(("http://", "https://")):
            parsed = self.scraper.parse_document_with_llama_cloud(text_or_path)
            if parsed:
                return parsed
        return sanitize_untrusted_text(text_or_path)

    def web_search(self, product: ProductInput) -> list[str]:
        """Return list of supporting URLs provided in product input or discovered via Tavily."""
        if product.supporting_urls:
            return [str(url) for url in product.supporting_urls]
        if self.searcher:
            res = self.searcher.search_product(
                product.manufacturer_part_number, product.brand, product.short_description
            )
            return res.urls
        return []

    def tavily_search(self, query: str) -> str:
        """Search the web via Tavily API for datasheets or spec sheets using custom query."""
        if not self.searcher:
            return "Tavily web search is not configured (missing TAVILY_API_KEY)."
        try:
            raw = self.searcher.client.search(query=query, search_depth="advanced", max_results=5)
            results = raw.get("results", [])
            if not results:
                return f"No web search results found for query: {query}"
            return "\n\n".join(
                f"Title: {r.get('title')}\nURL: {r.get('url')}\nContent: {r.get('content')}"
                for r in results
            )
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return f"Tavily search error: {exc}"

    def scrape_product_url(self, url: str) -> str:
        """Scrape a single product webpage using Playwright and BeautifulSoup."""
        page = self.scraper.scrape(url)
        return page.to_agent_text()

    def scrape_product_urls(self, urls: list[str]) -> str:
        """Scrape multiple product URLs in batch using Playwright."""
        pages = self.scraper.scrape_many(urls)
        return "\n\n".join(page.to_agent_text() for page in pages)

    def auto_search_and_scrape(self, mpn: str, brand: str, short_description: str) -> str:
        """Automatically discover product pages via Tavily search and scrape them with Playwright."""
        if not self.searcher:
            return "Web search is disabled. Please provide explicit supporting URLs or set TAVILY_API_KEY."

        search_res = self.searcher.search_product(mpn, brand, short_description)
        urls = search_res.urls
        if not urls:
            return f"No search results found for {brand} {mpn}."

        logger.info("Auto-discovered %d URLs for %s %s. Scraping with Playwright...", len(urls), brand, mpn)
        scraped_text = self.scrape_product_urls(urls[:3])
        return f"=== Tavily Discovered Snippets ===\n{search_res.to_agent_text()}\n\n=== Playwright Scraped Web Pages ===\n{scraped_text}"

