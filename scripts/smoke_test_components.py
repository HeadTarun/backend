import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.smoke_test_agent import InMemoryProductStore
from product_agent.orchestrator import ProductIntelligenceOrchestrator


def main() -> None:
    store = InMemoryProductStore()
    orchestrator = ProductIntelligenceOrchestrator(store=store)  # type: ignore[arg-type]
    statuses = orchestrator.component_status()

    assert statuses
    assert all(status.linked for status in statuses)
    assert orchestrator.tools.store is orchestrator.store
    assert orchestrator.tools.scraper is orchestrator.scraper

    print("component link smoke test passed")
    for status in statuses:
        print(f"{status.name}: {status.detail}")


if __name__ == "__main__":
    main()
