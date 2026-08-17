import logging
import re
from typing import Any

from product_agent.config import Settings, get_settings
from product_agent.guardrails import build_pii_middleware, sanitize_untrusted_text
from product_agent.schemas import ComponentStatus, Confidence, ProductInput, ProductIntelligence, ProductSpec, SourceEvidence
from product_agent.scraper import ProductPageScraper
from product_agent.storage import ProductStore
from product_agent.tools import AgentTools

logger = logging.getLogger(__name__)


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

        self.scraper = scraper or ProductPageScraper()
        searcher = ProductWebSearcher(settings.tavily_api_key, settings.tavily_max_results) if settings.tavily_api_key else None
        self.tools = tools or AgentTools(self.store, scraper=self.scraper, searcher=searcher)
        self.middleware = build_pii_middleware()
        # Lazily-built deep agents; HF is tried first, Ollama is the fallback.
        self._hf_agent = agent      # can be injected for testing
        self._ollama_agent: Any = None


    def process_product(self, product: ProductInput) -> ProductIntelligence:
        # Step 1: ALWAYS perform automatic web search & Playwright scraping first
        logger.info("Scraping product sources & web searching for MPN=%s...", product.manufacturer_part_number)
        source_text = self._collect_source_text(product)
        clean_input = product.model_copy(update={"supporting_text": sanitize_untrusted_text(source_text)})

        # Step 2: retrieve similar products from database for reference / consistency checks
        try:
            matches = self.tools.retrieve_similar_products(clean_input)
        except Exception as exc:
            logger.warning("Similar products lookup failed for MPN=%s: %s", product.manufacturer_part_number, exc)
            matches = []

        # Step 3: generate structured intelligence using LLM deep agent
        agent_result = self._run_deep_agent(clean_input)
        structured = agent_result if agent_result is not None else self._build_baseline_product(clean_input, matches)

        if agent_result is None:
            logger.warning(
                "Both LLMs unavailable; using regex baseline for MPN=%s",
                product.manufacturer_part_number,
            )

        # Step 4: save / update structured product intelligence in Supabase rag_products table
        try:
            logger.info("Saving freshly scraped & generated intelligence for MPN=%s into database...", product.manufacturer_part_number)
            return self.tools.save_structured_output(structured)
        except Exception as exc:
            logger.error(
                "save_structured_output failed for MPN=%s: %s",
                product.manufacturer_part_number, exc,
            )
            raise RuntimeError(
                f"Storage save failed for MPN '{product.manufacturer_part_number}': {exc}"
            ) from exc


    def _run_deep_agent(self, product: ProductInput) -> ProductIntelligence | None:
        """Invoke the deep agent with HuggingFace first, Ollama as fallback.

        Returns None when both LLMs fail, triggering the regex baseline.
        """
        try:
            from product_agent.deep_agent import create_product_deep_agent, deep_agent_input
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not import deep_agent: %s", exc)
            return None

        try:
            agent_in = deep_agent_input(product)
        except Exception as exc:
            logger.warning("Could not build deep agent input: %s", exc)
            return None

        # ----- Try each LLM backend in order -----
        for label, getter in [
            ("HuggingFace", self._get_hf_agent),
            ("Ollama",      self._get_ollama_agent),
        ]:
            agent = getter(create_product_deep_agent)
            if agent is None:
                continue
            result = self._invoke_agent(agent, agent_in, label)
            if result is not None:
                return result

        return None

    # ------------------------------------------------------------------
    # Agent builder helpers
    # ------------------------------------------------------------------

    def _get_hf_agent(self, factory: Any) -> Any | None:
        """Lazily build and cache the HuggingFace-backed deep agent."""
        if self._hf_agent is not None:
            return self._hf_agent
        try:
            from product_agent.llm import build_qwen_vl_chat_model
            model = build_qwen_vl_chat_model(self._settings)
            self._hf_agent = factory(
                settings=self._settings,
                store=self.store,
                tools=self.tools,
                scraper=self.scraper,
                model=model,
            )
            logger.info("Deep agent: using HuggingFace Qwen VLM.")
            return self._hf_agent
        except Exception as exc:
            logger.warning("Could not build HuggingFace deep agent: %s", exc)
            return None

    def _get_ollama_agent(self, factory: Any) -> Any | None:
        """Lazily build and cache the Ollama-backed deep agent (local fallback)."""
        if self._ollama_agent is not None:
            return self._ollama_agent
        try:
            from product_agent.llm import build_ollama_qwen_model
            model = build_ollama_qwen_model(self._settings)
            self._ollama_agent = factory(
                settings=self._settings,
                store=self.store,
                tools=self.tools,
                scraper=self.scraper,
                model=model,
            )
            logger.info("Deep agent: falling back to local Ollama Qwen3.")
            return self._ollama_agent
        except Exception as exc:
            logger.warning("Could not build Ollama deep agent: %s", exc)
            return None

    def _invoke_agent(self, agent: Any, agent_in: dict, label: str) -> ProductIntelligence | None:
        """Call agent.invoke() and parse the last AI message as ProductIntelligence JSON."""
        try:
            result = agent.invoke(agent_in)
            messages = result.get("messages", [])
            for msg in reversed(messages):
                content = getattr(msg, "content", None) or (
                    msg.get("content") if isinstance(msg, dict) else None
                )
                if not content:
                    continue
                # Strip markdown code fences the model may have added
                text = content.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```[a-z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text.strip())
                try:
                    return ProductIntelligence.model_validate_json(text)
                except Exception:
                    continue
            logger.warning("%s agent returned no parseable ProductIntelligence message.", label)
            return None
        except Exception as exc:
            logger.warning("%s agent invocation failed: %s", label, exc)
            return None

    def _collect_source_text(self, product: ProductInput) -> str | None:
        chunks = [product.supporting_text] if product.supporting_text else []
        if product.supporting_urls:
            try:
                scraped = self.tools.scrape_product_urls([str(url) for url in product.supporting_urls])
            except Exception as exc:
                chunks.append(f"Scraping failed for supporting URLs: {exc}")
            else:
                chunks.append(scraped)
        elif self.tools.searcher:
            try:
                scraped = self.tools.auto_search_and_scrape(
                    product.manufacturer_part_number,
                    product.brand,
                    product.short_description,
                )
            except Exception as exc:
                chunks.append(f"Automatic web search & scraping failed: {exc}")
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
