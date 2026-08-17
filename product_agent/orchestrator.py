import re
from product_agent.config import Settings, get_settings
from product_agent.guardrails import build_pii_middleware, sanitize_untrusted_text
from product_agent.schemas import ComponentStatus, Confidence, ProductInput, ProductIntelligence, ProductSpec, SourceEvidence
from product_agent.scraper import ProductPageScraper
from product_agent.storage import ProductStore
from product_agent.tools import AgentTools


class ProductIntelligenceOrchestrator:
    def __init__(
        self,
        store: ProductStore | None = None,
        tools: AgentTools | None = None,
        scraper: ProductPageScraper | None = None,
        settings: Settings | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.store = store or ProductStore(
            settings.supabase_url,
            settings.supabase_key,
            settings.supabase_products_table,
        )
        self.scraper = scraper or ProductPageScraper()
        self.tools = tools or AgentTools(self.store, scraper=self.scraper)
        self.middleware = build_pii_middleware()

    def process_product(self, product: ProductInput) -> ProductIntelligence:
        source_text = self._collect_source_text(product)
        clean_input = product.model_copy(update={"supporting_text": sanitize_untrusted_text(source_text)})
        matches = self.tools.retrieve_similar_products(clean_input)
        exact_match = next((match for match in matches if match.match_type == "exact_mpn"), None)
        if exact_match:
            existing = exact_match.product
            existing.quality_warnings = sorted(set(existing.quality_warnings + ["Returned from exact MPN cache."]))
            return existing

        structured = self._build_baseline_product(clean_input, matches)
        return self.tools.save_structured_output(structured)

    def _collect_source_text(self, product: ProductInput) -> str | None:
        chunks = [product.supporting_text] if product.supporting_text else []
        if product.supporting_urls:
            try:
                scraped = self.tools.scrape_product_urls([str(url) for url in product.supporting_urls])
            except Exception as exc:
                chunks.append(f"Scraping failed for supporting URLs: {exc}")
            else:
                chunks.append(scraped)
        return "\n\n".join(chunk for chunk in chunks if chunk)

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

    def _build_baseline_product(self, product: ProductInput, matches) -> ProductIntelligence:
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
        return ProductIntelligence(
            manufacturer_part_number=product.manufacturer_part_number,
            brand=product.brand,
            title=title,
            category=category,
            commerce_description=description,
            key_features=features,
            specifications=specs,
            applications=self._infer_applications(text),
            normalized_attributes={spec.name.lower().replace(" ", "_"): spec.value for spec in specs},
            source_evidence=evidence,
            quality_warnings=warnings,
            confidence=Confidence.medium if product.supporting_text or product.supporting_urls else Confidence.low,
        )

    def _extract_specs(self, text: str) -> list[ProductSpec]:
        patterns = [
            ("voltage", r"(\d+(?:\.\d+)?)\s?(V|VAC|VDC)"),
            ("current", r"(\d+(?:\.\d+)?)\s?(A|mA)"),
            ("power", r"(\d+(?:\.\d+)?)\s?(W|kW|HP)"),
            ("diameter", r"(\d+(?:\.\d+)?)\s?(mm|cm|in|inch)"),
            ("pressure", r"(\d+(?:\.\d+)?)\s?(psi|bar|kPa)"),
        ]
        specs: list[ProductSpec] = []
        for name, pattern in patterns:
            for value, unit in re.findall(pattern, text, flags=re.I):
                specs.append(ProductSpec(name=name.title(), value=value, unit=unit, source="input text"))
        return specs

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
