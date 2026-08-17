"""Tavily-powered web search for automatic product page discovery.

Usage
-----
When a ``TAVILY_API_KEY`` is present in the environment, the orchestrator
automatically searches the web for product specification pages instead of
requiring the user to supply URLs manually.

The search strategy:
1. Build a focused query: ``<brand> <MPN> <short_description> specifications datasheet``
2. Call Tavily Search (advanced depth) to get the top ``max_results`` pages.
3. Return both the discovered URLs (for Playwright scraping) and the Tavily-
   extracted snippet text (as a fast, non-JS fallback).
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class TavilySearchResult:
    url: str
    title: str
    content: str          # Tavily-extracted snippet
    score: float = 0.0


@dataclass
class ProductSearchResults:
    query: str
    results: list[TavilySearchResult] = field(default_factory=list)

    @property
    def urls(self) -> list[str]:
        return [r.url for r in self.results]

    def to_agent_text(self) -> str:
        """Flatten all snippets into a single text block for LLM consumption."""
        chunks = [f"Web search query: {self.query}"]
        for r in self.results:
            chunks.append(
                f"Source: {r.url}\nTitle: {r.title}\nContent: {r.content}"
            )
        return "\n\n".join(chunks)


class ProductWebSearcher:
    """Searches the web across all sites on the internet for product specification pages via the Tavily API."""

    def __init__(self, api_key: str, max_results: int = 5) -> None:

        self.client: Any = None
        self.max_results = max_results
        try:
            from tavily import TavilyClient
            self.client = TavilyClient(api_key=api_key)
        except ImportError:
            logger.warning("`tavily-python` package not installed. Run `pip install tavily-python` to enable automatic web search.")
        except Exception as exc:
            logger.warning("Could not initialize Tavily client: %s", exc)


    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search_product(
        self,
        manufacturer_part_number: str,
        brand: str,
        short_description: str,
    ) -> ProductSearchResults:
        """Search Tavily for product specification pages and return results.

        The search is run twice in parallel intent:
        - Primary query: exact MPN + brand for datasheet/spec pages.
        - Fallback: if primary returns < 2 results, broader description query.
        """
        query = self._build_query(manufacturer_part_number, brand, short_description)
        logger.info("Tavily search: %r", query)
        if not self.client:
            logger.warning("Tavily client unavailable; skipping automatic search.")
            return ProductSearchResults(query=query)

        try:
            raw = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=self.max_results,
                include_answer=False,
            )

        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return ProductSearchResults(query=query)

        results = [
            TavilySearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
            )
            for r in raw.get("results", [])
            if r.get("url")
        ]
        logger.info("Tavily returned %d results for MPN=%s", len(results), manufacturer_part_number)
        return ProductSearchResults(query=query, results=results)

    def extract_from_urls(self, urls: list[str]) -> str:
        """Use Tavily Extract to pull clean text from a list of URLs (no JS needed).

        Falls back gracefully if Extract is not supported by the current plan.
        """
        if not urls:
            return ""
        try:
            raw = self.client.extract(urls=urls[:5])  # Tavily Extract limit
            chunks = []
            for r in raw.get("results", []):
                text = r.get("raw_content") or r.get("content", "")
                if text:
                    chunks.append(f"Source: {r.get('url', '')}\n{text}")
            return "\n\n".join(chunks)
        except Exception as exc:
            logger.warning("Tavily extract failed (falling back to snippets): %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_query(mpn: str, brand: str, short_description: str) -> str:
        """Build a focused product search query."""
        # Prioritise exact MPN matches which give the most specific results
        return f'"{mpn}" {brand} {short_description} specifications datasheet'
