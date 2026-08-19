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
    def __init__(self, *, timeout_ms: int = 30000, max_chars: int = 8000, max_retries: int = 3) -> None:
        # Increase default Playwright timeout to 30s and allow a small retry count for HTTP fetches
        self.timeout_ms = timeout_ms
        self.max_chars = max_chars
        self.max_retries = max_retries

    def scrape(self, url: str) -> ScrapedProductPage:
        html = self._fetch_html(url)
        return self._parse(url, html)

    def scrape_many(self, urls: list[str]) -> list[ScrapedProductPage]:
        if not urls:
            return []

        # If any URL looks like a PDF, avoid Playwright and fetch via HTTP
        pdf_urls = [u for u in urls if u.lower().endswith(".pdf")]
        non_pdf_urls = [u for u in urls if not u.lower().endswith(".pdf")]

        pages: list[ScrapedProductPage] = []

        # Handle PDFs first via HTTP download/parsing
        for url in pdf_urls:
            try:
                html = self._fetch_pdf_as_html(url)
                pages.append(self._parse(url, html))
            except Exception as exc:
                logger.warning("PDF fetch/parse failed for %s: %s", url, exc)
                pages.append(ScrapedProductPage(url=url, title=None, description=None, text="", structured_data=[], image_urls=[]))

        # Try Playwright with a single browser instance for non-PDF pages
        if non_pdf_urls and sync_playwright is not None:
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                        )
                    )
                    for url in non_pdf_urls:
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

        # Fallback for all remaining URLs using httpx
        for url in non_pdf_urls:
            pages.append(self.scrape(url))
        return pages

    def _fetch_html(self, url: str) -> str:
        # If URL looks like a PDF, download and convert to simple HTML text
        if url.lower().endswith(".pdf"):
            return self._fetch_pdf_as_html(url)

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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
        last_exc = None
        for attempt in range(1, max(1, self.max_retries) + 1):
            try:
                resp = httpx.get(url, headers=headers, timeout=self.timeout_ms / 1000, follow_redirects=True)
                # If remote returned a PDF despite URL, handle it
                ctype = resp.headers.get("content-type", "")
                if "application/pdf" in ctype.lower() or url.lower().endswith(".pdf"):
                    return self._fetch_pdf_as_html(url, resp.content)
                return resp.text
            except Exception as exc:
                last_exc = exc
                logger.warning("HTTP fetch attempt %d failed for %s: %s", attempt, url, exc)
        logger.warning("HTTP fetch failed for %s after %d attempts: %s", url, self.max_retries, last_exc)
        return f"<html><body><p>Failed to scrape {url}: {last_exc}</p></body></html>"

    def _fetch_pdf_as_html(self, url: str, content: bytes | None = None) -> str:
        """Download a PDF (or use provided bytes) and return a simple HTML text representation.
        Uses pdfplumber if available; otherwise embeds a download link and filename.
        """
        try:
            import io
            import httpx
            try:
                import pdfplumber
            except Exception:
                pdfplumber = None

            if content is None:
                # download the PDF bytes
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
                resp = httpx.get(url, headers=headers, timeout=max(10, self.timeout_ms / 1000), follow_redirects=True)
                content = resp.content

            if pdfplumber:
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text_parts = []
                    for p in pdf.pages[:10]:
                        page_text = p.extract_text() or ""
                        text_parts.append(page_text)
                    joined = "\n\n".join(text_parts)
                    html = f"<html><body><pre>{self._normalize_whitespace(joined)[:20000]}</pre></body></html>"
                    return html
            else:
                # Return a small HTML stub pointing to the PDF bytes (saved externally by caller if desired)
                return f"<html><body><p>PDF document at {url} (pdfplumber not installed to extract text).</p></body></html>"
        except Exception as exc:
            logger.warning("Failed to convert PDF to HTML for %s: %s", url, exc)
            return f"<html><body><p>Failed to scrape PDF {url}: {exc}</p></body></html>"

    def _best_effort_wait(self, page: Any) -> None:
        try:
            # Wait a little longer for network to quiet down; cap at 10s for responsiveness
            page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 10000))
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
