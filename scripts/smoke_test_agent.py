import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_agent.orchestrator import ProductIntelligenceOrchestrator
from product_agent.schemas import ProductInput, ProductIntelligence, RetrievalMatch


class InMemoryProductStore:
    def __init__(self) -> None:
        self.saved: list[ProductIntelligence] = []

    def exact_match(self, mpn: str, brand: str) -> ProductIntelligence | None:
        for product in self.saved:
            if product.manufacturer_part_number.upper() == mpn.upper() and product.brand.lower() == brand.lower():
                return product
        return None

    def search(self, query: str, limit: int = 5) -> list[RetrievalMatch]:
        return []

    def save(self, product: ProductIntelligence) -> ProductIntelligence:
        self.saved.append(product)
        return product

    def list_products(self, limit: int = 50) -> list[ProductIntelligence]:
        return self.saved[-limit:]


def main() -> None:
    store = InMemoryProductStore()
    orchestrator = ProductIntelligenceOrchestrator(store=store)  # type: ignore[arg-type]
    statuses = orchestrator.component_status()
    assert all(status.linked for status in statuses)
    assert orchestrator.tools.store is store
    assert orchestrator.tools.scraper is orchestrator.scraper

    product_input = ProductInput(
        manufacturer_part_number="S-100",
        brand="ACME",
        short_description="24 VDC proximity sensor",
        supporting_text=(
            "ACME S-100 is a 24 VDC proximity sensor with stainless steel housing. "
            "It is designed for PLC automation and conveyor applications."
        ),
    )

    result = orchestrator.process_product(product_input)
    generated_json = result.model_dump_json(indent=2)

    assert result.manufacturer_part_number == "S-100"
    assert result.brand == "ACME"
    assert result.category == "Sensors"
    assert any(spec.name == "Voltage" and spec.value == "24" for spec in result.specifications)
    assert "Industrial automation" in result.applications
    assert store.saved and store.saved[0] == result

    cached = orchestrator.process_product(product_input)
    assert "Returned from exact MPN cache." in cached.quality_warnings

    print("agent smoke test passed")
    print(generated_json)


if __name__ == "__main__":
    main()
