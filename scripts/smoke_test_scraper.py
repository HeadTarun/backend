import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_agent.scraper import ProductPageScraper


def main() -> None:
    html = """
    <html>
      <head>
        <title>ACME S-100 Sensor</title>
        <meta name="description" content="24 VDC industrial proximity sensor for automation lines">
        <script type="application/ld+json">
          {"@type": "Product", "name": "ACME S-100", "sku": "S-100", "brand": "ACME"}
        </script>
      </head>
      <body>
        <main>
          <h1>ACME S-100 Sensor</h1>
          <p>24 VDC proximity sensor with stainless steel housing.</p>
          <p>Designed for industrial automation and conveyor applications.</p>
        </main>
      </body>
    </html>
    """

    page = ProductPageScraper()._parse("https://example.com/products/s-100", html)

    assert page.title == "ACME S-100 Sensor"
    assert page.description == "24 VDC industrial proximity sensor for automation lines"
    assert page.structured_data
    assert page.structured_data[0]["name"] == "ACME S-100"
    assert "24 VDC proximity sensor" in page.text

    print("scraper smoke test passed")


if __name__ == "__main__":
    main()
