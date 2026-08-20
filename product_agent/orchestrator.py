import logging
import re
from typing import Any
from urllib.parse import quote_plus

from product_agent.config import Settings, get_settings
from product_agent.guardrails import build_pii_middleware, sanitize_untrusted_text
from product_agent.schemas import ComponentStatus, Confidence, ProductInput, ProductIntelligence, ProductSpec, SourceEvidence
from product_agent.scraper import ProductPageScraper
from product_agent.storage import ProductStore
from product_agent.tools import AgentTools

logger = logging.getLogger(__name__)

# Keys that should NEVER appear as spec names (scraper/search metadata)
_IGNORED_SPEC_KEYS = frozenset({
    "url", "title", "meta description", "visible page text", "structured data",
    "product images", "source", "web search query", "mpn", "brand",
    "supporting urls", "http", "https", "short description", "supporting text",
    "quality warnings", "content", "score", "query", "excerpt", "locator",
    "source type", "match type", "confidence", "created at", "category",
    "traceability", "traceability evidence",
})


def _strip_scraper_headers(text: str) -> str:
    """Remove scraper boilerplate header lines before spec extraction."""
    skip_prefixes = (
        "url:", "title:", "meta description:", "visible page text:",
        "structured data:", "product images:", "source:",
        "web search query:", "content:", "score:", "query:",
    )
    lines = []
    for line in text.splitlines():
        lower = line.strip().lower()
        if any(lower.startswith(p) for p in skip_prefixes):
            continue
        lines.append(line)
    return "\n".join(lines)


class ProductIntelligenceOrchestrator:
    def __init__(
        self,
        store: ProductStore | None = None,
        tools: AgentTools | None = None,
        scraper: ProductPageScraper | None = None,
        settings: Settings | None = None,
        agent: Any | None = None,
    ) -> None:
        settings = settings or get_settings()
        self._settings = settings
        self.store = store or ProductStore(
            settings.supabase_url,
            settings.supabase_key,
            settings.supabase_products_table,
        )

        from product_agent.web_search import ProductWebSearcher
        from product_agent.evaluation import configure_langsmith
        configure_langsmith(settings)

        self.scraper = scraper or ProductPageScraper()
        searcher = ProductWebSearcher(settings.tavily_api_key, settings.tavily_max_results) if settings.tavily_api_key else None
        self.tools = tools or AgentTools(self.store, scraper=self.scraper, searcher=searcher)
        self.middleware = build_pii_middleware()
        self._agent = agent

    def process_product(self, product: ProductInput) -> ProductIntelligence:
        # Step 1: Scrape URLs / web-search, collect text AND product images
        logger.info("Scraping product sources & web searching for MPN=%s...", product.manufacturer_part_number)
        source_text, extracted_images = self._collect_sources(product)
        clean_input = product.model_copy(update={"supporting_text": sanitize_untrusted_text(source_text)})

        # Step 2: retrieve similar products from database for reference / consistency checks
        try:
            matches = self.tools.retrieve_similar_products(clean_input)
        except Exception as exc:
            logger.warning("Similar products lookup failed for MPN=%s: %s", product.manufacturer_part_number, exc)
            matches = []

        # Step 3: generate structured intelligence using the deterministic regex baseline
        structured = self._build_baseline_product(clean_input, matches, image_urls=extracted_images)

        if getattr(product, "custom_image_url", None):
            custom_img = product.custom_image_url.strip()
            if custom_img:
                if custom_img in extracted_images:
                    extracted_images.remove(custom_img)
                extracted_images.insert(0, custom_img)

        # Always guarantee an image (real scraped URL, or branded placeholder)
        if not extracted_images:
            label = quote_plus(f"{product.brand} {product.manufacturer_part_number}")
            extracted_images = [f"https://placehold.co/600x400/1e293b/94a3b8.png?text={label}"]

        structured.images = list(dict.fromkeys(extracted_images + (structured.images or [])))
        if getattr(product, "custom_image_url", None) and product.custom_image_url.strip():
            structured.image_url = product.custom_image_url.strip()
        elif not structured.image_url:
            structured.image_url = structured.images[0]

        # STEP 4a: ALWAYS extract specs from the raw short_description first (guaranteed baseline)
        # This runs BEFORE any LLM filtering so these specs can never be lost
        baseline_specs = self._extract_specs(product.short_description)
        baseline_names = {s.name.lower() for s in baseline_specs}

        # Step 4b: Also scan scraped text (with headers stripped)
        text_to_scan = _strip_scraper_headers(clean_input.supporting_text or "")
        if text_to_scan:
            for spec in self._extract_specs(text_to_scan):
                if spec.name.lower() not in baseline_names:
                    baseline_specs.append(spec)
                    baseline_names.add(spec.name.lower())
        regex_specs = baseline_specs

        # Filter garbage metadata entries from LLM spec list
        structured.specifications = [
            s for s in structured.specifications
            if s.name.lower() not in _IGNORED_SPEC_KEYS
            and not s.name.lower().startswith("http")
            and len(s.value.strip()) > 0
        ]

        # Merge regex specs not already present
        existing_names = {s.name.lower() for s in structured.specifications}
        for spec in regex_specs:
            if spec.name.lower() not in existing_names:
                structured.specifications.append(spec)
                existing_names.add(spec.name.lower())

        # Always rebuild normalized_attributes from final spec list
        for spec in structured.specifications:
            key = spec.name.lower().replace(" ", "_").replace("/", "")
            if key not in structured.normalized_attributes:
                structured.normalized_attributes[key] = f"{spec.value} {spec.unit or ''}".strip()

        # Step 5: persist to Supabase (fault-tolerant)
        try:
            logger.info("Saving intelligence for MPN=%s into database...", product.manufacturer_part_number)
            return self.tools.save_structured_output(structured)
        except Exception as exc:
            logger.warning(
                "save_structured_output notice for MPN=%s (returning in-memory result): %s",
                product.manufacturer_part_number, exc,
            )
            structured.quality_warnings.append(f"Database save notice: saved to memory cache ({exc})")
            return structured



    def _collect_sources(self, product: ProductInput) -> tuple[str | None, list[str]]:
        chunks: list[str] = []
        if product.supporting_text:
            chunks.append(product.supporting_text)

        image_urls: list[str] = []
        urls_to_scrape = [str(u) for u in product.supporting_urls]

        # If user gave no URLs, try Tavily web search to discover them (only if web searcher available)
        if not urls_to_scrape and self.tools.searcher:
            try:
                search_res = self.tools.searcher.search_product(
                    product.manufacturer_part_number,
                    product.brand,
                    product.short_description,
                )
                urls_to_scrape = search_res.urls[:3]
                if getattr(search_res, "image_urls", None):
                    image_urls.extend(search_res.image_urls)
                # Add Tavily snippet text only (skip header lines)
                for r in search_res.results:
                    if r.content:
                        chunks.append(r.content)
            except Exception as exc:
                logger.warning("Tavily web search failed: %s", exc)

        # Playwright-scrape each URL; collect visible text and images
        if urls_to_scrape:
            try:
                pages = self.scraper.scrape_many(urls_to_scrape)
                scraped_imgs: list[str] = []
                for page in pages:
                    # Only append visible product text — NOT the full page header block
                    if page.text:
                        chunks.append(page.text)
                    scraped_imgs.extend(page.image_urls)
                    # Supplement with JSON-LD description/name fields
                    for block in page.structured_data:
                        for field in ("description", "name"):
                            val = block.get(field, "")
                            if val and isinstance(val, str):
                                chunks.append(val)
                # If user supplied URLs, place scraped images at top of image_urls
                if product.supporting_urls:
                    image_urls = scraped_imgs + image_urls
                else:
                    image_urls.extend(scraped_imgs)
            except Exception as exc:
                logger.warning("Scraping failed: %s", exc)

        # Web image search fallback ONLY if URLs were provided or Tavily was active, but scraping yielded no images
        if not image_urls and (product.supporting_urls or self.tools.searcher):
            try:
                from product_agent.web_search import search_duckduckgo_images
                ddg_imgs = search_duckduckgo_images(f"{product.brand} {product.manufacturer_part_number} product", max_results=5)
                image_urls.extend(ddg_imgs)
            except Exception as exc:
                logger.warning("Direct web image fallback search failed: %s", exc)

        combined = "\n\n".join(c for c in chunks if c)
        dedup_images: list[str] = []
        for img in image_urls:
            if img and img not in dedup_images:
                dedup_images.append(img)
        return (combined[:5000] if combined else None, dedup_images)


    def batch(self, products: list[ProductInput]) -> list[ProductIntelligence]:
        return [self.process_product(product) for product in products]

    def component_status(self) -> list[ComponentStatus]:
        return [
            ComponentStatus(name="storage", linked=self.store is self.tools.store, detail="Agent tools use orchestrator storage."),
            ComponentStatus(name="scraper", linked=self.scraper is self.tools.scraper, detail="Agent tools use orchestrator scraper."),
            ComponentStatus(name="retrieval", linked=True, detail="Orchestrator calls AgentTools.retrieve_similar_products before generation."),
            ComponentStatus(name="persistence", linked=True, detail="Orchestrator saves generated ProductIntelligence through AgentTools."),
            ComponentStatus(name="guardrails", linked=True, detail="Scraped and supplied source text is sanitized before extraction."),
        ]

    def _build_baseline_product(self, product: ProductInput, matches, image_urls: list[str] | None = None) -> ProductIntelligence:
        text = product.supporting_text or product.short_description
        specs = self._extract_specs(text)
        category = self._infer_category(product.short_description)
        features = self._extract_features(text)
        evidence = [
            SourceEvidence(
                source_type="input",
                locator="short_description",
                excerpt=product.short_description[:300],
                confidence=Confidence.medium,
            )
        ]
        for url in product.supporting_urls:
            evidence.append(SourceEvidence(source_type="url", locator=str(url), excerpt="Provided by user.", confidence=Confidence.low))

        warnings = []
        if not product.supporting_text and not product.supporting_urls:
            warnings.append("No supporting source material was provided; output is inferred from minimal input.")
        if matches:
            warnings.append("Similar saved products were used for consistency checks.")

        title = f"{product.brand} {product.manufacturer_part_number} {product.short_description}".strip()
        description = self._commerce_description(product, category, features)

        extracted_images = image_urls or []
        primary_image = extracted_images[0] if extracted_images else None

        normalized = {spec.name.lower().replace(" ", "_"): f"{spec.value} {spec.unit or ''}".strip() for spec in specs}

        return ProductIntelligence(
            manufacturer_part_number=product.manufacturer_part_number,
            brand=product.brand,
            title=title,
            category=category,
            commerce_description=description,
            image_url=primary_image,
            images=extracted_images,
            key_features=features,
            specifications=specs,
            applications=self._infer_applications(text),
            normalized_attributes=normalized,
            source_evidence=evidence,
            quality_warnings=warnings,
            confidence=Confidence.medium if product.supporting_text or product.supporting_urls else Confidence.low,
        )

    def _extract_specs(self, text: str) -> list[ProductSpec]:
        if not text or not text.strip():
            return []

        patterns = [
            # Voltage: 24VDC, 230/400V, 24 VAC — require V immediately or with space
            ("Voltage",          r"\b(\d+(?:[/.]\d+)*)\s*(V(?:AC|DC)?|Volts?)(?=\b|\s|$)"),
            # Current: 200mA, 4A — prevent matching 'A' inside words (require space or start)
            ("Current",          r"(?<![A-Za-z])(\d+(?:\.\d+)?)\s*(mA|Amps?|(?<![A-Za-z])A(?![A-Za-z]))"),
            # Power: 1.5 kW, 0.37kW — 'W' must be whole word or kW/MW
            ("Power",            r"\b(\d+(?:\.\d+)?)\s*(kW|MW|HP|Horsepower|W(?!\w))"),
            # Frequency: 50Hz, 60/50Hz
            ("Frequency",        r"\b(\d+(?:/\d+)?)\s*(Hz|kHz|MHz)\b"),
            # Temperature: -25...+70°C, -40 to 85°C
            ("Temperature",      r"(-?\d+(?:\.\d+)?(?:\s*(?:to|\.\.\.|~|-{1,2})\s*[-+]?\d+(?:\.\d+)?)?)\s*(°C|°F|deg\s*[CF])\b"),
            # Pressure: 6 bar, 100 psi
            ("Pressure",         r"\b(\d+(?:\.\d+)?)\s*(psi|bar|kPa|MPa)\b"),
            # Speed: 1420 RPM
            ("Speed",            r"\b(\d+(?:\.\d+)?)\s*(RPM)\b"),
            # Weight: 500 g, 1.2 kg — require space before unit to avoid matching 'g' in words
            ("Weight",           r"\b(\d+(?:\.\d+)?)\s+(kg|lbs?)\b|\b(\d+(?:\.\d+)?)\s+(g)\b(?=\s|$)"),
            # Diameter/Size: 18mm, 12.5 cm
            ("Diameter / Size",  r"\b(\d+(?:\.\d+)?)\s*(mm|cm|in|inch(?:es)?)\b"),
            # Thread: M18, M12
            ("Thread Size",      r"\b(M\d{1,3})\b"),
            # Output: PNP, NPN, NO, NC
            ("Output Type",      r"\b(PNP|NPN|NO\+NC|NO|NC|4[-\s]?20\s*mA|0[-\s]?10\s*V)\b"),
            # Enclosure: IP67, IP65
            ("Enclosure Rating", r"\b(IP6[5-9]|IP[4-9]\d|NEMA\s*\d+[AX]?)\b"),
        ]

        specs: list[ProductSpec] = []
        seen_names: set[str] = set()

        for name, pattern in patterns:
            key = name.lower()
            if key in seen_names:
                continue
            try:
                for match in re.finditer(pattern, text, flags=re.I):
                    groups = [g for g in match.groups() if g is not None]
                    if len(groups) >= 2:
                        val, unit = groups[0], groups[1]
                    elif len(groups) == 1:
                        val, unit = groups[0], None
                    else:
                        val, unit = match.group(0), None

                    val_str = str(val).strip()
                    if val_str and val_str not in ("0", ""):
                        seen_names.add(key)
                        specs.append(ProductSpec(name=name, value=val_str, unit=unit, source="extracted_spec"))
                        break  # one canonical value per spec name
            except re.error:
                continue

        # Secondary: key-value pairs separated by ':', '-', or '=' e.g. "Housing Material: Stainless Steel", "Sensing Range - 5mm"
        try:
            kv_matches = re.findall(r"([A-Z0-9][a-zA-Z0-9 /()_-]{1,35})\s*[:=-]\s*([^\n;|<>{}\[\]]{1,80})", text)
            for raw_name, raw_val in kv_matches:
                name_clean = raw_name.strip()
                val_clean = raw_val.strip().rstrip(".,;")
                name_lower = name_clean.lower()
                # Skip values that look like URLs or are too long or metadata
                if (
                    name_lower in _IGNORED_SPEC_KEYS
                    or name_lower in seen_names
                    or name_lower.startswith("http")
                    or not val_clean
                    or val_clean.lower().startswith("http")
                    or len(val_clean) > 80
                ):
                    continue

                # Attempt to parse embedded unit from value e.g. "5 mm", "24VDC"
                unit_parsed = None
                unit_match = re.search(r"^([-\d./]+)\s*([a-zA-Z°]+(?:AC|DC)?)$", val_clean)
                if unit_match and len(val_clean) < 20:
                    val_clean = unit_match.group(1).strip()
                    unit_parsed = unit_match.group(2).strip()

                seen_names.add(name_lower)
                specs.append(ProductSpec(name=name_clean, value=val_clean, unit=unit_parsed, source="extracted_spec"))
        except Exception:
            pass

        return specs[:25]

    def _extract_features(self, text: str) -> list[str]:
        chunks = re.split(r"[.;\n]", text)
        features = [chunk.strip(" -") for chunk in chunks if 12 <= len(chunk.strip()) <= 120]
        return features[:6] or ["Structured product profile generated from available product identifiers."]

    def _infer_category(self, description: str) -> str:
        desc = description.lower()
        category_map = {
            "motor": "Motors and Drives",
            "sensor": "Sensors",
            "valve": "Valves",
            "bearing": "Bearings",
            "pump": "Pumps",
            "switch": "Switches",
            "relay": "Relays",
            "cable": "Cables and Connectivity",
        }
        for keyword, category in category_map.items():
            if keyword in desc:
                return category
        return "Industrial Components"

    def _infer_applications(self, text: str) -> list[str]:
        lowered = text.lower()
        applications = []
        if "automation" in lowered or "plc" in lowered:
            applications.append("Industrial automation")
        if "hydraulic" in lowered or "pneumatic" in lowered:
            applications.append("Fluid power systems")
        if "conveyor" in lowered or "motor" in lowered:
            applications.append("Material handling")
        return applications or ["General industrial maintenance and procurement"]

    def _commerce_description(self, product: ProductInput, category: str, features: list[str]) -> str:
        feature_text = features[0].rstrip(".")
        return (
            f"{product.brand} {product.manufacturer_part_number} is a {category.lower()} product for industrial commerce catalogs. "
            f"{feature_text}. Validate critical fit, ratings, and certifications against manufacturer documentation before purchase."
        )
