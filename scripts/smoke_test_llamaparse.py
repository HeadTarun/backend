"""Smoke test for LlamaParse document intelligence integration in ProductPageScraper."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_agent.scraper import ProductPageScraper


def main() -> None:
    print("Testing LlamaParse integration in ProductPageScraper...")
    scraper = ProductPageScraper()

    if not scraper.llama_api_key:
        print("⚠️ LLAMA_CLOUD_API_KEY / LLAMAPARSE_API_KEY not found in env.")
        print("   LlamaParse integration is gracefully initialized & ready when key is set.")
    else:
        print("✅ LlamaParse API Key detected!")

    print("\nVerifying scraper methods...")
    assert hasattr(scraper, "parse_document_with_llamaparse"), "Scraper missing parse_document_with_llamaparse method"
    
    print("✅ LlamaParse integration smoke test passed!")


if __name__ == "__main__":
    main()
