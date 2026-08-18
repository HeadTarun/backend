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
    image_urls: list[str] = field(default_factory=list)

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


def search_duckduckgo_images(query: str, max_results: int = 5) -> list[str]:
    """Fallback search that directly queries DuckDuckGo for product images without needing an API key."""
    import httpx
    import re
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        with httpx.Client(headers=headers, timeout=6.0, follow_redirects=True) as client:
            res = client.get("https://duckduckgo.com/", params={"q": query})
            vqd_match = re.search(r'vqd=["\']([^"\']+)["\']', res.text) or re.search(r'vqd=([\d-]+)', res.text)
            if not vqd_match:
                return []
            vqd = vqd_match.group(1)
            img_res = client.get(
                "https://duckduckgo.com/i.js",
                params={"l": "us-en", "o": "json", "q": query, "vqd": vqd},
            )
            data = img_res.json()
            results = data.get("results", [])
            images: list[str] = []
            for r in results:
                img_url = r.get("image")
                if img_url and isinstance(img_url, str) and img_url.startswith("http"):
                    if not any(skip in img_url.lower() for skip in ["logo", "icon", "blank", "avatar", "loader", "sprite", "pixel", "1x1", "tracking"]):
                        if img_url not in images:
                            images.append(img_url)
            return images[:max_results]
    except Exception as exc:
        logger.warning("DuckDuckGo image search failed: %s", exc)
        return []


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
        """Search Tavily for product specification pages and return results."""
        query = self._build_query(manufacturer_part_number, brand, short_description)
        logger.info("Tavily search: %r", query)
        image_urls: list[str] = []

        if not self.client:
            logger.warning("Tavily client unavailable; attempting direct DuckDuckGo image fallback.")
            ddg_imgs = search_duckduckgo_images(f"{brand} {manufacturer_part_number} product", max_results=5)
            return ProductSearchResults(query=query, image_urls=ddg_imgs)

        try:
            raw = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=self.max_results,
                include_images=True,
                include_answer=False,
            )
            # Tavily returns image URLs under "images" key
            raw_imgs = raw.get("images", [])
            for img in raw_imgs:
                if isinstance(img, str) and img.startswith("http"):
                    image_urls.append(img)
                elif isinstance(img, dict) and img.get("url"):
                    image_urls.append(img["url"])

        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            ddg_imgs = search_duckduckgo_images(f"{brand} {manufacturer_part_number} product", max_results=5)
            return ProductSearchResults(query=query, image_urls=ddg_imgs)

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

        if not image_urls:
            image_urls = search_duckduckgo_images(f"{brand} {manufacturer_part_number} product", max_results=5)

        logger.info("Tavily returned %d web results and %d images for MPN=%s", len(results), len(image_urls), manufacturer_part_number)
        return ProductSearchResults(query=query, results=results, image_urls=image_urls)

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
