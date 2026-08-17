from product_agent.guardrails import sanitize_untrusted_text
from product_agent.scraper import ProductPageScraper
from product_agent.schemas import ProductInput, ProductIntelligence, RetrievalMatch
from product_agent.storage import ProductStore


class AgentTools:
    def __init__(self, store: ProductStore, scraper: ProductPageScraper | None = None) -> None:
        self.store = store
        self.scraper = scraper or ProductPageScraper()

    def retrieve_similar_products(self, product: ProductInput, limit: int = 5) -> list[RetrievalMatch]:
        exact = self.store.exact_match(product.manufacturer_part_number, product.brand)
        if exact:
            return [RetrievalMatch(score=1.0, match_type="exact_mpn", product=exact)]
        query = f"{product.brand} {product.manufacturer_part_number} {product.short_description}"
        return self.store.search(query, limit=limit)

    def save_structured_output(self, product: ProductIntelligence) -> ProductIntelligence:
        return self.store.save(product)

    def parse_doc_or_image(self, text: str | None) -> str | None:
        return sanitize_untrusted_text(text)

    def web_search(self, product: ProductInput) -> list[str]:
        return [str(url) for url in product.supporting_urls]

    def scrape_product_url(self, url: str) -> str:
        page = self.scraper.scrape(url)
        return page.to_agent_text()

    def scrape_product_urls(self, urls: list[str]) -> str:
        pages = self.scraper.scrape_many(urls)
        return "\n\n".join(page.to_agent_text() for page in pages)
