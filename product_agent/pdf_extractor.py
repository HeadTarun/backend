import io
import json
import logging
import re
from typing import Any

import pypdf
from langchain_core.messages import SystemMessage, HumanMessage

from product_agent.llm import build_gateway_chat_model
from product_agent.schemas import ExtractedPDFProductItem, PDFExtractionResponse

logger = logging.getLogger(__name__)

KNOWN_INDUSTRIAL_BRANDS = [
    "Schneider Electric", "Schneider", "Siemens", "Festo", "Omron", "ABB", "SKF",
    "SMC", "Allen-Bradley", "Rockwell Automation", "Mitsubishi Electric", "Mitsubishi",
    "Bosch Rexroth", "Bosch", "Phoenix Contact", "Eaton", "Sick", "Pepperl+Fuchs",
    "Danfoss", "Wago", "Turck", "Honeywell", "Parker Hannifin", "Parker",
    "Keyence", "Endress+Hauser", "Yokogawa", "Emerson", "Yaskawa", "IFM Electronic", "IFM",
    "Weidmuller", "B&R", "Beckhoff", "Pilz", "Banner Engineering", "Balluff",
    "FAG", "NSK", "NTN", "Timken", "Koyo", "Kuka", "Fanuc", "Delta Electronics",
]

_MPN_REGEX = re.compile(r"\b([A-Z0-9]{2,}[-_/][A-Z0-9-_/]{2,}|[0-9]+[A-Z]{2,}[0-9A-Z-_]*|[A-Z]{2,}[0-9]{2,}[0-9A-Z-_]*)\b", re.IGNORECASE)
_QTY_REGEX = re.compile(r"(?:qty|quantity|count|nos|pcs|units?)\s*[:=]?\s*(\d+)|(\d+)\s*(?:pcs|nos|units|ea)\b", re.IGNORECASE)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract raw text from PDF binary content using pypdf."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text: list[str] = []
    for idx, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages_text.append(f"--- Page {idx + 1} ---\n{page_text.strip()}")
    return "\n\n".join(pages_text)


def parse_products_with_heuristics(raw_text: str) -> list[ExtractedPDFProductItem]:
    """Fallback rule-based heuristic parser for Bills of Materials (BOM) & tables."""
    items: list[ExtractedPDFProductItem] = []
    seen_mpns: set[str] = set()

    for line in raw_text.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("--- Page"):
            continue

        # Look for brand
        detected_brand = "Generic / Unspecified"
        for brand in KNOWN_INDUSTRIAL_BRANDS:
            if re.search(rf"\b{re.escape(brand)}\b", line_clean, re.IGNORECASE):
                detected_brand = brand
                break

        # Look for MPN candidates
        mpn_matches = _MPN_REGEX.findall(line_clean)
        if not mpn_matches:
            # Check if there's a token with mixed alphanumeric characters (e.g. XS618B1PAL2)
            tokens = line_clean.split()
            for token in tokens:
                cleaned_token = token.strip(" ,;:()[]{}")
                if len(cleaned_token) >= 4 and any(c.isdigit() for c in cleaned_token) and any(c.isalpha() for c in cleaned_token):
                    mpn_matches.append(cleaned_token)

        if not mpn_matches:
            continue

        mpn = mpn_matches[0].strip(" ,;:()[]{}")
        if mpn.upper() in seen_mpns or len(mpn) < 3:
            continue

        seen_mpns.add(mpn.upper())

        # Look for quantity
        qty = None
        qty_match = _QTY_REGEX.search(line_clean)
        if qty_match:
            qty_str = qty_match.group(1) or qty_match.group(2)
            if qty_str and qty_str.isdigit():
                qty = int(qty_str)

        # Build clean description from the line
        desc = line_clean
        # Remove the MPN and brand from the description line if present
        desc = re.sub(re.escape(mpn), "", desc, flags=re.IGNORECASE).strip()
        if detected_brand != "Generic / Unspecified":
            desc = re.sub(re.escape(detected_brand), "", desc, flags=re.IGNORECASE).strip()
        desc = re.sub(r"\s+", " ", desc).strip(" -:,|")

        if not desc:
            desc = f"Industrial product part {mpn}"

        items.append(
            ExtractedPDFProductItem(
                manufacturer_part_number=mpn,
                brand=detected_brand,
                short_description=desc,
                quantity=qty,
                category="Industrial Automation / MRO",
                supporting_text=line_clean,
            )
        )

    return items


def parse_products_with_llm(raw_text: str) -> list[ExtractedPDFProductItem] | None:
    """Use AI Gateway / LLM to accurately extract structured product list from PDF text."""
    try:
        chat_model = build_gateway_chat_model()
        truncated_text = raw_text[:12000]

        system_msg = SystemMessage(
            content=(
                "You are an industrial product intelligence AI specialized in extracting product lists, "
                "Bills of Materials (BOM), Request for Quotes (RFQs), purchase orders, equipment schedules, and catalogs from PDF documents.\n"
                "Extract every unique industrial product mentioned in the document.\n"
                "Return STRICTLY valid JSON without conversational text or markdown explanation, in this exact schema:\n"
                "{\n"
                '  "products": [\n'
                "    {\n"
                '      "manufacturer_part_number": "exact part number / MPN",\n'
                '      "brand": "Manufacturer or Brand name (e.g. Festo, Schneider Electric, Siemens)",\n'
                '      "short_description": "Precise product description, specs, or dimensions",\n'
                '      "quantity": 10,\n'
                '      "category": "e.g. Sensors, Pneumatics, Motors, Bearings",\n'
                '      "supporting_text": "Relevant line context or raw spec notes from the PDF"\n'
                "    }\n"
                "  ]\n"
                "}"
            )
        )
        user_msg = HumanMessage(
            content=f"Extract all industrial products from the following PDF document text:\n\n{truncated_text}"
        )

        response = chat_model.invoke([system_msg, user_msg])
        content = response.content if hasattr(response, "content") else str(response)

        # Clean JSON markdown blocks
        cleaned = re.sub(r"```(?:json)?", "", content).strip()
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            cleaned = json_match.group(0)

        data = json.loads(cleaned)
        raw_items = data.get("products", [])
        if not raw_items and isinstance(data, list):
            raw_items = data

        extracted: list[ExtractedPDFProductItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            mpn = str(item.get("manufacturer_part_number") or item.get("mpn") or "").strip()
            if not mpn:
                continue
            brand = str(item.get("brand") or item.get("manufacturer") or "Generic / Unspecified").strip()
            desc = str(item.get("short_description") or item.get("description") or f"Industrial part {mpn}").strip()
            qty = item.get("quantity")
            if qty is not None:
                try:
                    qty = int(qty)
                except (ValueError, TypeError):
                    qty = None
            category = item.get("category")
            supp = item.get("supporting_text")

            extracted.append(
                ExtractedPDFProductItem(
                    manufacturer_part_number=mpn,
                    brand=brand,
                    short_description=desc,
                    quantity=qty,
                    category=category,
                    supporting_text=supp,
                )
            )

        if extracted:
            return extracted
    except Exception as exc:
        logger.warning("LLM PDF product extraction failed, falling back to heuristics: %s", exc)

    return None


def extract_products_from_pdf(pdf_bytes: bytes, filename: str = "document.pdf") -> PDFExtractionResponse:
    """End-to-end extraction: reads PDF, parses text, and extracts structured product list."""
    warnings: list[str] = []
    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
    except Exception as exc:
        logger.error("Failed to parse PDF binary for %s: %s", filename, exc)
        return PDFExtractionResponse(
            filename=filename,
            total_products_found=0,
            raw_text_length=0,
            products=[],
            warnings=[f"Failed to read PDF file: {exc}"],
        )

    if not raw_text.strip():
        return PDFExtractionResponse(
            filename=filename,
            total_products_found=0,
            raw_text_length=0,
            products=[],
            warnings=["No readable text found in PDF. It may be a scanned image or empty."],
        )

    products = parse_products_with_llm(raw_text)
    if not products:
        products = parse_products_with_heuristics(raw_text)
        if products:
            warnings.append("Parsed products using rule-based table extractor (LLM unavailable or returned empty).")
        else:
            warnings.append("No industrial part numbers or product items could be recognized in the document.")

    return PDFExtractionResponse(
        filename=filename,
        total_products_found=len(products),
        raw_text_length=len(raw_text),
        products=products,
        warnings=warnings,
    )
