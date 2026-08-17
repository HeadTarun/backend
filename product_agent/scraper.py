import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]

from product_agent.guardrails import sanitize_untrusted_text


PRODUCT_SELECTORS = [
    "[itemtype*='Product']",
    "[data-testid*='product' i]",
    "[class*='product' i]",
    "main",
    "article",
    "body",
]


@dataclass(frozen=True)
class ScrapedProductPage:
    url: str
    title: str | None
    description: str | None
    text: str
    structured_data: list[dict[str, Any]]

    def to_agent_text(self, max_chars: int = 8000) -> str:
        chunks = [f"URL: {self.url}"]
        if self.title:
            chunks.append(f"Title: {self.title}")
        if self.description:
            chunks.append(f"Meta description: {self.description}")
        if self.structured_data:
            chunks.append(f"Structured data: {json.dumps(self.structured_data[:3], ensure_ascii=True)}")
        if self.text:
            chunks.append(f"Visible page text: {self.text}")
        return "\n".join(chunks)[:max_chars]


class ProductPageScraper:
    def __init__(self, *, timeout_ms: int = 20000, max_chars: int = 8000) -> None:
        self.timeout_ms = timeout_ms
        self.max_chars = max_chars

    def scrape(self, url: str) -> ScrapedProductPage:
        html = self._fetch_html(url)
        return self._parse(url, html)

    def scrape_many(self, urls: list[str]) -> list[ScrapedProductPage]:
        if not urls:
            return []

        # Try Playwright with a single browser instance
        if sync_playwright is not None:
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                        )
                    )
                    pages: list[ScrapedProductPage] = []
                    for url in urls:
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                            self._best_effort_wait(page)
                            html = page.content()
                            pages.append(self._parse(url, html))
                        except Exception as exc:
                            logger.warning("Playwright failed for URL %s: %s (falling back to httpx)", url, exc)
                            html = self._fetch_html_httpx(url)
                            pages.append(self._parse(url, html))
                    browser.close()
                    return pages
            except Exception as exc:
                logger.warning("Playwright browser launch failed: %s (using HTTP fallback)", exc)

        # Fallback for all URLs using httpx
        return [self.scrape(url) for url in urls]

    def _fetch_html(self, url: str) -> str:
        if sync_playwright is not None:
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                        )
                    )
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                        self._best_effort_wait(page)
                        return page.content()
                    finally:
                        browser.close()
            except Exception as exc:
                logger.warning("Playwright scrape failed for %s: %s (using httpx)", url, exc)

        return self._fetch_html_httpx(url)

    def _fetch_html_httpx(self, url: str) -> str:
        import httpx
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
            resp = httpx.get(url, headers=headers, timeout=self.timeout_ms / 1000, follow_redirects=True)
            return resp.text
        except Exception as exc:
            logger.warning("HTTP fetch failed for %s: %s", url, exc)
            return f"<html><body><p>Failed to scrape {url}: {exc}</p></body></html>"


    def _best_effort_wait(self, page: Any) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 5000))
        except PlaywrightTimeoutError:
            pass

    def _parse(self, url: str, html: str) -> ScrapedProductPage:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = self._first_text(
            soup.select_one("h1"),
            soup.select_one("meta[property='og:title']"),
            soup.select_one("title"),
        )
        description = self._meta_content(soup, "description") or self._meta_content(soup, "og:description")
        structured_data = self._structured_product_data(html)
        visible_text = sanitize_untrusted_text(self._product_text(soup)) or ""

        return ScrapedProductPage(
            url=url,
            title=title,
            description=description,
            text=visible_text[: self.max_chars],
            structured_data=structured_data,
        )

    def _product_text(self, soup: BeautifulSoup) -> str:
        for selector in PRODUCT_SELECTORS:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if len(text) > 200:
                    return self._normalize_whitespace(text)
        return self._normalize_whitespace(soup.get_text(" ", strip=True))

    def _structured_product_data(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        blocks: list[dict[str, Any]] = []
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            blocks.extend(self._product_jsonld_blocks(data))
        return blocks[:5]

    def _product_jsonld_blocks(self, data: Any) -> list[dict[str, Any]]:
        items = data if isinstance(data, list) else [data]
        products: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                products.extend(self._product_jsonld_blocks(graph))
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "product" for value in types):
                products.append(item)
        return products

    def _first_text(self, *elements: Any) -> str | None:
        for element in elements:
            if not element:
                continue
            text = element.get("content") if hasattr(element, "get") else None
            text = text or element.get_text(" ", strip=True)
            if text:
                return self._normalize_whitespace(text)
        return None

    def _meta_content(self, soup: BeautifulSoup, name: str) -> str | None:
        element = soup.select_one(f"meta[name='{name}'], meta[property='{name}']")
        if not element:
            return None
        content = element.get("content")
        if not isinstance(content, str):
            return None
        return self._normalize_whitespace(content) if content else None

    def _normalize_whitespace(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
