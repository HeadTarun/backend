import io
import sys
from pathlib import Path

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
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
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


def test_quick():
    pdf_bytes = create_sample_bom_pdf()
    text = extract_text_from_pdf(pdf_bytes)
    assert "XS618B1PAL2" in text
    assert "DNC-32-100-PPV-A" in text

    items = parse_products_with_heuristics(text)
    assert len(items) == 4
    assert items[0].manufacturer_part_number == "XS618B1PAL2"
    assert items[0].brand == "Schneider Electric"
    assert items[0].quantity == 12

    client = TestClient(app)
    res = client.post(
        "/upload-pdf-extract",
        files={"file": ("bom.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_products_found"] == 4
    assert len(data["products"]) == 4

    print("QUICK PDF EXTRACTION UNIT TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_quick()
