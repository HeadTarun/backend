import json
import logging
import re
from dataclasses import dataclass, field
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
    image_urls: list[str] = field(default_factory=list)

    def to_agent_text(self, max_chars: int = 8000) -> str:
        chunks = [f"URL: {self.url}"]
        if self.title:
            chunks.append(f"Title: {self.title}")
        if self.description:
            chunks.append(f"Meta description: {self.description}")
        if self.image_urls:
            chunks.append(f"Product Images: {self.image_urls[:3]}")
        if self.structured_data:
            chunks.append(f"Structured data: {json.dumps(self.structured_data[:3], ensure_ascii=True)}")
        if self.text:
            chunks.append(f"Visible page text: {self.text}")
        return "\n".join(chunks)[:max_chars]


class ProductPageScraper:
    def __init__(self, *, timeout_ms: int = 8000, max_chars: int = 8000) -> None:
        self.timeout_ms = timeout_ms
        self.max_chars = max_chars

    def scrape(self, url: str) -> ScrapedProductPage:
        html = self._fetch_html(url)
        return self._parse(url, html)

    def scrape_many(self, urls: list[str]) -> list[ScrapedProductPage]:
        if not urls:
            return []
        return [self.scrape(url) for url in urls]

    def _fetch_html(self, url: str) -> str:
        return self._fetch_html_httpx(url)

    def _fetch_html_httpx(self, url: str) -> str:
        import httpx
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            resp = httpx.get(
                url,
                headers=headers,
                timeout=max(self.timeout_ms / 1000, 5.0),
                follow_redirects=True,
            )
            return resp.text
        except Exception as exc:
            logger.debug("HTTP fetch failed for %s: %s", url, exc)
            return f"<html><body><p>Failed to scrape {url}: {exc}</p></body></html>"


    def _best_effort_wait(self, page: Any) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 5000))
        except PlaywrightTimeoutError:
            pass

    def _parse(self, url: str, html: str) -> ScrapedProductPage:
        from urllib.parse import urljoin
        soup = BeautifulSoup(html, "html.parser")

        # Extract images before decomposition
        image_urls: list[str] = []
        skip_terms = ["logo", "icon", "blank", "avatar", "loader", "button", "sprite", "pixel", "1x1", "tracking", "cart", "checkout", "banner", "footer", "nav"]

        def _add_valid_image(url_str: str, priority_insert: bool = False) -> None:
            if not url_str or not url_str.strip():
                return
            abs_url = urljoin(url, url_str.strip())
            if abs_url.startswith("http") and not any(skip in abs_url.lower() for skip in skip_terms):
                if abs_url not in image_urls:
                    if priority_insert:
                        image_urls.insert(0, abs_url)
                    else:
                        image_urls.append(abs_url)

        # 1. Meta tags (highest priority)
        meta_imgs = [
            self._meta_content(soup, "og:image"),
            self._meta_content(soup, "og:image:secure_url"),
            self._meta_content(soup, "twitter:image"),
            self._meta_content(soup, "twitter:image:src"),
            self._meta_content(soup, "image"),
        ]
        for meta_img in meta_imgs:
            if meta_img:
                _add_valid_image(meta_img)

        link_img = soup.select_one("link[rel='image_src']")
        if link_img and link_img.get("href"):
            _add_valid_image(str(link_img.get("href")))

        # 2. JSON-LD Structured Data
        structured_data = self._structured_product_data(html)
        for block in structured_data:
            img = block.get("image")
            if isinstance(img, str):
                _add_valid_image(img, priority_insert=True)
            elif isinstance(img, list):
                for item in img:
                    if isinstance(item, str):
                        _add_valid_image(item, priority_insert=True)
                    elif isinstance(item, dict) and item.get("url"):
                        _add_valid_image(str(item.get("url")), priority_insert=True)

        # 3. Microdata & Product-Specific Containers
        product_selectors = [
            "[itemprop='image']",
            "[class*='product-image' i] img",
            "[class*='product-photo' i] img",
            "[class*='product-media' i] img",
            "[class*='main-image' i] img",
            "[id*='product-image' i] img",
            "[id*='main-image' i] img",
            ".gallery-image img",
            ".product-gallery img",
        ]
        for sel in product_selectors:
            for elem in soup.select(sel):
                for attr in ["src", "data-src", "data-zoom-image", "data-large-image", "data-high-res-src", "content", "href"]:
                    val = elem.get(attr)
                    if isinstance(val, str) and val.strip():
                        _add_valid_image(val)

        # 4. Picture source tags
        for source_tag in soup.select("picture source"):
            raw_srcset = source_tag.get("srcset") or source_tag.get("data-srcset")
            if isinstance(raw_srcset, str) and raw_srcset.strip():
                src_val = raw_srcset.strip().split(",")[0].split()[0]
                _add_valid_image(src_val)

        # 5. General img tags
        for img_tag in soup.select("img"):
            for attr in ["src", "data-src", "data-original", "data-lazy-src", "data-zoom-image", "data-high-res-src", "data-large-image", "data-product-image", "data-image", "data-image-src", "srcset", "data-srcset"]:
                raw_src = img_tag.get(attr)
                if isinstance(raw_src, str) and raw_src.strip():
                    src_val = raw_src.strip().split(",")[0].split()[0]
                    _add_valid_image(src_val)

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = self._first_text(
            soup.select_one("h1"),
            soup.select_one("meta[property='og:title']"),
            soup.select_one("title"),
        )
        description = self._meta_content(soup, "description") or self._meta_content(soup, "og:description")
        visible_text = sanitize_untrusted_text(self._product_text(soup)) or ""

        return ScrapedProductPage(
            url=url,
            title=title,
            description=description,
            text=visible_text[: self.max_chars],
            structured_data=structured_data,
            image_urls=image_urls[:6],
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
