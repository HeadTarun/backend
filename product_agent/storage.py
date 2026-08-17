from typing import Any, cast

try:
    from supabase import create_client
except ImportError:
    create_client = None  # type: ignore[assignment]

from product_agent.schemas import ProductIntelligence, RetrievalMatch
from dotenv import load_dotenv
load_dotenv()


Row = dict[str, object]


def _response_rows(data: object) -> list[Row]:
    if not isinstance(data, list):
        return []
    return [cast(Row, row) for row in data if isinstance(row, dict)]


def _row_text(row: Row, key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


class ProductStore:
    def __init__(self, supabase_url: str | None, supabase_key: str | None, table_name: str = "products") -> None:
        if create_client is None:
            raise RuntimeError("Install dependencies with `uv sync` before starting the Supabase-backed app.")
        if not supabase_url or not supabase_key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY before starting the app.")
        self.table_name = table_name
        self.client: Any = create_client(supabase_url, supabase_key)

    def save(self, product: ProductIntelligence) -> ProductIntelligence:
        payload = product.model_dump(mode="json")
        row = {
            "mpn": product.manufacturer_part_number.upper(),
            "brand": product.brand.lower(),
            "title": product.title,
            "description": product.commerce_description,
            "payload": payload,
            "created_at": product.created_at.isoformat(),
        }
        self.client.table(self.table_name).upsert(row, on_conflict="mpn,brand").execute()
        return product

    def exact_match(self, mpn: str, brand: str) -> ProductIntelligence | None:
        response = (
            self.client.table(self.table_name)
            .select("payload")
            .eq("mpn", mpn.upper())
            .eq("brand", brand.lower())
            .limit(1)
            .execute()
        )
        rows = _response_rows(response.data)
        if not rows:
            return None
        payload = rows[0].get("payload")
        if payload is None:
            return None
        return ProductIntelligence.model_validate(payload)

    def search(self, query: str, limit: int = 5) -> list[RetrievalMatch]:
        terms = {term.lower() for term in query.split() if len(term) > 2}
        matches: list[RetrievalMatch] = []
        response = self.client.table(self.table_name).select("payload,title,description").limit(250).execute()
        for row in _response_rows(response.data):
            haystack = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            if overlap:
                payload = row.get("payload")
                if payload is None:
                    continue
                product = ProductIntelligence.model_validate(payload)
                matches.append(RetrievalMatch(score=overlap / max(len(terms), 1), match_type="semantic-lite", product=product))
        return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]

    def list_products(self, limit: int = 50) -> list[ProductIntelligence]:
        response = (
            self.client.table(self.table_name)
            .select("payload")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        products: list[ProductIntelligence] = []
        for row in _response_rows(response.data):
            payload = row.get("payload")
            if payload is not None:
                products.append(ProductIntelligence.model_validate(payload))
        return products
