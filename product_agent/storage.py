import logging
from typing import Any, cast

try:
    from supabase import create_client
except ImportError:
    create_client = None  # type: ignore[assignment]

from product_agent.schemas import ProductIntelligence, RetrievalMatch
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

Row = dict[str, object]


def _response_rows(data: object) -> list[Row]:
    if not isinstance(data, list):
        return []
    return [cast(Row, row) for row in data if isinstance(row, dict)]


def _row_text(row: Row, key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


class ProductStore:
    """Hybrid storage engine using Supabase PostgreSQL with in-memory fallback."""

    def __init__(self, supabase_url: str | None = None, supabase_key: str | None = None, table_name: str | None = None) -> None:
        from product_agent.config import get_settings
        settings = get_settings()
        supabase_url = supabase_url or settings.supabase_url
        supabase_key = supabase_key or settings.supabase_key
        table_name = table_name or settings.supabase_products_table or "products"

        self.table_name = table_name
        self.client: Any = None
        self._memory_cache: dict[tuple[str, str], ProductIntelligence] = {}

        if create_client is not None and supabase_url and supabase_key:
            try:
                self.client = create_client(supabase_url, supabase_key)
                logger.info("ProductStore initialized connected to Supabase table '%s'.", self.table_name)
            except Exception as exc:
                logger.warning("Could not initialize Supabase client (using in-memory store): %s", exc)


    def save(self, product: ProductIntelligence) -> ProductIntelligence:
        key = (product.manufacturer_part_number.upper(), product.brand.lower())
        self._memory_cache[key] = product

        if self.client:
            payload = product.model_dump(mode="json")
            row = {
                "mpn": product.manufacturer_part_number.upper(),
                "brand": product.brand.lower(),
                "title": product.title,
                "description": product.commerce_description,
                "payload": payload,
                "created_at": product.created_at.isoformat(),
            }
            try:
                self.client.table(self.table_name).upsert(row, on_conflict="mpn,brand").execute()
            except Exception as exc:
                logger.warning("Supabase save failed for MPN=%s (cached in-memory): %s", product.manufacturer_part_number, exc)

        return product

    def exact_match(self, mpn: str, brand: str) -> ProductIntelligence | None:
        key = (mpn.upper(), brand.lower())
        if key in self._memory_cache:
            return self._memory_cache[key]

        if self.client:
            try:
                response = (
                    self.client.table(self.table_name)
                    .select("payload")
                    .eq("mpn", mpn.upper())
                    .eq("brand", brand.lower())
                    .limit(1)
                    .execute()
                )
                rows = _response_rows(response.data)
                if rows and rows[0].get("payload"):
                    prod = ProductIntelligence.model_validate(rows[0]["payload"])
                    self._memory_cache[key] = prod
                    return prod
            except Exception as exc:
                logger.warning("Supabase exact_match lookup failed: %s", exc)

        return None

    def search(self, query: str, limit: int = 5) -> list[RetrievalMatch]:
        terms = {term.lower() for term in query.split() if len(term) > 2}
        matches: list[RetrievalMatch] = []

        if self.client:
            try:
                response = self.client.table(self.table_name).select("payload,title,description").limit(250).execute()
                for row in _response_rows(response.data):
                    haystack = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
                    overlap = sum(1 for term in terms if term in haystack)
                    if overlap and row.get("payload"):
                        product = ProductIntelligence.model_validate(row["payload"])
                        matches.append(RetrievalMatch(score=overlap / max(len(terms), 1), match_type="semantic-lite", product=product))
                if matches:
                    return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]
            except Exception as exc:
                logger.warning("Supabase search failed: %s", exc)

        # Fallback search over memory cache
        for prod in self._memory_cache.values():
            haystack = f"{prod.title} {prod.commerce_description}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            if overlap:
                matches.append(RetrievalMatch(score=overlap / max(len(terms), 1), match_type="semantic-lite", product=prod))

        return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]

    def list_products(self, limit: int = 50) -> list[ProductIntelligence]:
        if self.client:
            try:
                response = (
                    self.client.table(self.table_name)
                    .select("payload")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                products: list[ProductIntelligence] = []
                for row in _response_rows(response.data):
                    if row.get("payload"):
                        products.append(ProductIntelligence.model_validate(row["payload"]))
                if products:
                    return products
            except Exception as exc:
                logger.warning("Supabase list_products failed: %s", exc)

        return list(self._memory_cache.values())[:limit]

