import io
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pypdf
from fastapi.testclient import TestClient
from product_agent.api import app
from product_agent.pdf_extractor import (
    extract_products_from_pdf,
    extract_text_from_pdf,
    parse_products_with_heuristics,
)


def create_sample_bom_pdf() -> bytes:
    """Create a minimalist valid PDF binary with sample BOM products."""
    writer = pypdf.PdfWriter()
    # Add a blank page with text annotation or create a PDF stream
    # Alternatively use pypdf PageObject
    page = writer.add_blank_page(width=612, height=792)
    
    # We can write plain PDF stream content or test using text extraction
    # Standard PDF text stream
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 380 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"50 720 Td (PROCUREMENT BILL OF MATERIALS) Tj\n"
        b"0 -25 Td (Item 1: Schneider Electric XS618B1PAL2 Inductive proximity sensor 18mm 24VDC Qty: 12 pcs) Tj\n"
        b"0 -25 Td (Item 2: Festo DNC-32-100-PPV-A Compact pneumatic cylinder 32mm bore stroke 100mm Qty: 4 pcs) Tj\n"
        b"0 -25 Td (Item 3: Siemens 1LA7096-4AA10 3-phase asynchronous motor 1.5 kW 230/400V Qty: 2 pcs) Tj\n"
        b"0 -25 Td (Item 4: SKF 6205-2RS1 Deep groove ball bearing contact seals Qty: 20 pcs) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000676 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"755\n"
        b"%%EOF\n"
    )
    return pdf_content


def main() -> None:
    print("Testing PDF Generation & Extraction...")
    pdf_bytes = create_sample_bom_pdf()
    assert len(pdf_bytes) > 0, "PDF bytes should not be empty"

    # Test raw text extraction
    text = extract_text_from_pdf(pdf_bytes)
    print(f"Extracted raw text length: {len(text)}")
    print(f"Extracted preview:\n{text}\n")
    assert "XS618B1PAL2" in text
    assert "DNC-32-100-PPV-A" in text
    assert "1LA7096-4AA10" in text
    assert "6205-2RS1" in text

    # Test heuristic fallback extractor
    heuristic_items = parse_products_with_heuristics(text)
    print(f"Heuristic extractor identified {len(heuristic_items)} products:")
    for item in heuristic_items:
        print(f" - MPN: {item.manufacturer_part_number} | Brand: {item.brand} | Qty: {item.quantity} | Desc: {item.short_description}")
    assert len(heuristic_items) >= 3, f"Expected at least 3 products extracted, got {len(heuristic_items)}"

    # Test end-to-end extraction helper
    res = extract_products_from_pdf(pdf_bytes, filename="test_bom.pdf")
    print(f"\nEnd-to-end extraction result: found {res.total_products_found} products in '{res.filename}'")
    assert res.total_products_found >= 3

    # Test FastAPI endpoints with TestClient
    print("\nTesting FastAPI /upload-pdf-extract endpoint...")
    client = TestClient(app)
    response = client.post(
        "/upload-pdf-extract",
        files={"file": ("test_bom.pdf", pdf_bytes, "application/pdf")},
    )
    print(f"API /upload-pdf-extract status: {response.status_code}")
    assert response.status_code == 200, f"API error: {response.text}"
    data = response.json()
    assert data["total_products_found"] >= 3
    assert len(data["products"]) >= 3
    print(f"API extracted {data['total_products_found']} products successfully.")

    print("\nTesting FastAPI /upload-pdf-process endpoint...")
    batch_response = client.post(
        "/upload-pdf-process",
        files={"file": ("test_bom.pdf", pdf_bytes, "application/pdf")},
    )
    print(f"API /upload-pdf-process status: {batch_response.status_code}")
    assert batch_response.status_code == 200, f"API batch error: {batch_response.text}"
    batch_data = batch_response.json()
    print(f"Batch processed count: {batch_data.get('processed_count')}")
    assert batch_data.get("processed_count", 0) >= 3

    print("\nALL PDF EXTRACTION AND BATCH PROCESSING SMOKE TESTS PASSED!")


if __name__ == "__main__":
    main()
