import json
import re
import httpx
import pandas as pd
import streamlit as st
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# Fixed backend endpoint (not exposed/editable by the client)
API_URL = "https://fackend.vercel.app"

# ---------------------------------------------------------------------------
# DATA CLEANUP HELPERS
# Raw scraped/LLM output often contains leftover markdown table fragments,
# stray headers, and "specs" that are really just repeated brand/datasheet
# mentions. These helpers filter that noise before anything reaches the UI.
# ---------------------------------------------------------------------------

def _looks_like_junk(text: str) -> bool:
    """True if a string is mostly separator/table-remnant characters."""
    if not text:
        return True
    t = text.strip()
    if len(t) < 2:
        return True
    non_separator = re.sub(r"[|\-\s_.:=+*#]", "", t)
    return (len(non_separator) / max(len(t), 1)) < 0.3


def _is_source_mention(name: str, value: str, brand: str) -> bool:
    """True if a 'spec' is really just a datasheet/brand reference, not a real spec."""
    name_l = name.lower()
    if "datasheet" in name_l:
        return True
    if brand and value.strip().lower() == brand.strip().lower():
        return True
    return False


def clean_specifications(specs, brand):
    """Split raw spec entries into real specs vs. brand/datasheet mentions, dropping junk."""
    real_specs, source_mentions, seen = [], [], set()
    for spec in specs or []:
        s_name = (spec.get("name") if isinstance(spec, dict) else getattr(spec, "name", "")) or ""
        s_val = str((spec.get("value") if isinstance(spec, dict) else getattr(spec, "value", "")) or "")
        s_unit = spec.get("unit") if isinstance(spec, dict) else getattr(spec, "unit", None)
        raw_src = (spec.get("source") if isinstance(spec, dict) else getattr(spec, "source", None)) or "extracted_spec"

        s_name, s_val = s_name.strip(), s_val.strip()
        if not s_name or not s_val:
            continue
        if _looks_like_junk(s_name) or _looks_like_junk(s_val):
            continue

        key = (s_name.lower(), s_val.lower())
        if key in seen:
            continue
        seen.add(key)

        if _is_source_mention(s_name, s_val, brand):
            source_mentions.append({"name": s_name, "value": s_val})
            continue

        real_specs.append({"name": s_name, "value": s_val, "unit": s_unit, "source": raw_src})
    return real_specs, source_mentions


def clean_features(features, max_items=8):
    """Strip markdown/table remnants from feature bullets and dedupe."""
    cleaned, seen = [], set()
    for feat in features or []:
        f = str(feat).strip()
        if _looks_like_junk(f):
            continue
        f = re.sub(r"^#+\s*", "", f)  # strip markdown headers
        f = f.strip("[]() ")
        if not f:
            continue
        key = f.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(f)
        if len(cleaned) >= max_items:
            break
    return cleaned


def clean_description(desc: str) -> str:
    """Remove markdown header markers and collapse whitespace in free-text descriptions."""
    if not desc:
        return desc
    d = re.sub(r"#+\s*", "", desc.strip())
    d = re.sub(r"\s+", " ", d)
    return d.strip()


def dedupe_normalized_attributes(norm_attrs: dict) -> dict:
    """Collapse keys that normalize to the same slug (e.g. 'diameter_/_size' vs 'diameter__size')."""
    result, seen_slugs = {}, set()
    for k, v in (norm_attrs or {}).items():
        slug = re.sub(r"[^a-z0-9]", "", k.lower())
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        result[k] = v
    return result


# ---------------------------------------------------------------------------
# OPTIONAL AI POLISH (Groq)
# The regex helpers above catch obvious junk cheaply and for free. Some noise
# survives because it's made of real words in a nonsense pairing (e.g. a spec
# named "Standard general" with value "purpose configuration") — a regex
# can't tell that's broken, but an LLM can. This runs via LangChain's Groq
# integration with structured output, so the model's response is validated
# against a schema instead of hand-parsed JSON. It's the primary path when a
# Groq key is configured, and always falls back to the regex-cleaned data if
# the call fails or returns something invalid.
# ---------------------------------------------------------------------------

GROQ_MODEL = "llama-3.3-70b-versatile"

GROQ_SYSTEM_PROMPT = (
    "You are a technical catalog editor for an industrial parts commerce site. "
    "You will receive product data that has already had obvious junk removed, "
    "but may still contain sentence fragments, near-duplicates, or entries that "
    "aren't genuine technical specifications (brand mentions, image captions, "
    "incomplete phrases). "
    "Rewrite the description as 1-2 clear sentences a buyer would actually "
    "read. Drop any specification that is not a genuine, complete technical "
    "attribute. Merge duplicate or near-duplicate specifications. Keep at most "
    "6 features, each a real, complete capability statement. Never invent "
    "values that are not present in the input — only clean up and reorganize "
    "what's given."
)


class PolishedSpec(BaseModel):
    name: str = Field(description="Specification name, e.g. 'Voltage'")
    value: str = Field(description="Specification value, e.g. '24'")
    unit: Optional[str] = Field(default=None, description="Unit, e.g. 'VDC', or null if none")


class PolishedListing(BaseModel):
    description: str = Field(description="A clean 1-2 sentence product description")
    specifications: List[PolishedSpec] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list, description="Up to 6 real feature statements")
    applications: List[str] = Field(default_factory=list)


@st.cache_data(show_spinner=False, ttl=3600)
def polish_with_groq(payload_json: str, api_key: str):
    """Send pre-cleaned product data to Groq (via LangChain) for a final
    readability pass, using structured output so the response is validated
    against a schema rather than hand-parsed. Returns a dict on success, or
    None on any failure (caller falls back to the regex-cleaned data).
    Cached so re-rendering the same product doesn't re-call the API."""
    try:
        llm = ChatGroq(model=GROQ_MODEL, api_key=api_key, temperature=0.2, timeout=20)
        structured_llm = llm.with_structured_output(PolishedListing)
        prompt = ChatPromptTemplate.from_messages([
            ("system", GROQ_SYSTEM_PROMPT),
            ("human", "{payload}"),
        ])
        chain = prompt | structured_llm
        result = chain.invoke({"payload": payload_json})
        return result.model_dump()
    except Exception:
        return None

st.set_page_config(
    page_title="Product Intelligence Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Modern Custom CSS Styling
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1E3A8A 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #475569;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
    }
    .product-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1.25rem;
    }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        background-color: #DBEAFE;
        color: #1E40AF;
    }
    .pdf-stat-card {
        background: #F1F5F9;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        border: 1px solid #CBD5E1;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .app-footer {
        text-align: center;
        color: #94A3B8;
        font-size: 0.8rem;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #E2E8F0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

MAX_PDF_SIZE_MB = 20

# AI polish runs automatically in the background whenever a Groq key is
# configured in secrets — the client never sees a toggle, key field, or any
# indication of whether a listing was AI-polished or fell back to the
# regex-cleaned version. It's invisible either way.
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else ""
AI_POLISH_ENABLED = bool(GROQ_API_KEY)

st.markdown('<div class="main-title">Product Intelligence Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Turn a part number, description, or product list into a ready-to-publish catalog entry</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("✨ Try an Example")
    st.caption("Load a sample product to see how it works")
    if st.button("Proximity Sensor"):
        st.session_state["mpn"] = "XS618B1PAL2"
        st.session_state["brand"] = "Schneider Electric"
        st.session_state["desc"] = "Inductive proximity sensor 18mm 24VDC PNP NO"
    if st.button("Industrial Motor"):
        st.session_state["mpn"] = "1LA7096-4AA10"
        st.session_state["brand"] = "Siemens"
        st.session_state["desc"] = "3-phase asynchronous motor 1.5 kW 230/400V 1420 RPM"
    if st.button("Pneumatic Cylinder"):
        st.session_state["mpn"] = "DNC-32-100-PPV-A"
        st.session_state["brand"] = "Festo"
        st.session_state["desc"] = "Double-acting compact cylinder 32 mm bore 100 mm stroke"

    st.markdown("---")
    st.markdown("### ℹ️ How it works")
    st.caption(
        "Provide a part number and description (and optionally a product link), "
        "and the assistant will research, structure, and enrich the listing for you."
    )

    st.markdown("---")
    if st.button("🔄 Start Over", use_container_width=True):
        for key in ("mpn", "brand", "desc", "pdf_extracted_data", "pdf_batch_results"):
            st.session_state.pop(key, None)
        st.rerun()

main_tab1, main_tab2 = st.tabs(["📦 Single Product Lookup", "📄 Upload Product List (PDF)"])

# ---------------------------------------------------------------------------
# TAB 1: SINGLE PRODUCT QUERY
# ---------------------------------------------------------------------------
with main_tab1:
    with st.form("single_product"):
        st.subheader("📦 Product Details")
        col1, col2 = st.columns(2)
        with col1:
            mpn = st.text_input(
                "Manufacturer Part Number (MPN)*",
                value=st.session_state.get("mpn", "XS618B1PAL2"),
                placeholder="e.g. XS618B1PAL2",
            )
            brand = st.text_input(
                "Brand / Manufacturer*",
                value=st.session_state.get("brand", "Schneider Electric"),
                placeholder="e.g. Schneider Electric",
            )
        with col2:
            desc = st.text_area(
                "Short Description*",
                value=st.session_state.get("desc", "Inductive proximity sensor 18mm M18 24VDC PNP NO"),
                placeholder="e.g. 24 VDC proximity sensor stainless steel",
                height=100,
            )

        product_website_url = st.text_input(
            "🌐 Product Page / Website URL (optional)",
            placeholder="https://www.example.com/product/XS618B1PAL2",
            help="Paste any manufacturer or distributor product URL to automatically pull in images and specs.",
        )

        with st.expander("📄 Additional Supporting Materials (optional)", expanded=False):
            urls = st.text_area("Additional Product URLs (one per line)", placeholder="https://example.com/datasheet.pdf")
            supporting_text = st.text_area(
                "Raw Spec / Catalog Text",
                placeholder="Paste raw spec sheets, user manuals, or catalog copy here...",
                height=100,
            )

        submitted = st.form_submit_button("🚀 Generate Product Listing", use_container_width=True)

    if mpn and len(mpn.strip()) < 4:
        st.caption("⚠️ That part number looks unusually short — double check it before submitting.")

    if submitted:
        if not mpn or not mpn.strip() or not brand or not brand.strip() or not desc or not desc.strip():
            st.error("Please fill in MPN, Brand, and Short description.")
        else:
            all_urls = []
            if product_website_url.strip():
                all_urls.append(product_website_url.strip())
            for line in urls.splitlines():
                if line.strip() and line.strip() not in all_urls:
                    all_urls.append(line.strip())

            payload = {
                "manufacturer_part_number": mpn.strip(),
                "brand": brand.strip(),
                "short_description": desc.strip(),
                "supporting_urls": all_urls,
                "supporting_text": supporting_text.strip() if supporting_text else None,
            }
            with st.spinner("🤖 Researching the product and building your listing..."):
                try:
                    response = httpx.post(f"{API_URL}/process-product", json=payload, timeout=300)
                except Exception as exc:
                    st.error(f"Something went wrong connecting to the service: {exc}")
                    response = None

            if response and response.is_success:
                result = response.json()
                st.success("✅ Product Listing Generated Successfully!")

                # --- Regex cleanup pass (free, instant, always runs as the safety net) ---
                real_specs, source_mentions = clean_specifications(result.get("specifications", []), result.get("brand", ""))
                clean_feats = clean_features(result.get("key_features", []))
                clean_apps = [str(a).strip() for a in result.get("applications", []) if str(a).strip()]
                clean_desc = clean_description(result.get("commerce_description"))

                # --- AI polish pass (primary path when configured; silent fallback otherwise) ---
                if AI_POLISH_ENABLED:
                    with st.spinner("🤖 Researching the product and building your listing..."):
                        polish_input = {
                            "description": clean_desc,
                            "specifications": [
                                {"name": s["name"], "value": s["value"], "unit": s["unit"]} for s in real_specs
                            ],
                            "features": clean_feats,
                            "applications": clean_apps,
                        }
                        polished = polish_with_groq(json.dumps(polish_input, ensure_ascii=False), GROQ_API_KEY)

                    if polished:
                        clean_desc = polished.get("description", clean_desc)
                        clean_feats = polished.get("features", clean_feats) or clean_feats
                        clean_apps = polished.get("applications", clean_apps) or clean_apps
                        polished_specs = polished.get("specifications")
                        if polished_specs:
                            real_specs = [
                                {
                                    "name": s.get("name", ""),
                                    "value": s.get("value", ""),
                                    "unit": s.get("unit"),
                                    "source": "extracted_spec",
                                }
                                for s in polished_specs
                                if s.get("name") and s.get("value")
                            ]
                    # If polish_with_groq returned None, real_specs/clean_feats/clean_apps/
                    # clean_desc simply keep their regex-cleaned values — no error, no
                    # indication to the client that anything different happened.

                # Top Overview Header
                st.markdown("---")
                col_img, col_info = st.columns([1, 2])

                with col_img:
                    st.markdown("#### 🖼️ Product Image")
                    all_images = result.get("images", [])
                    primary_img = result.get("image_url")

                    real_images = [img for img in all_images if "placehold.co" not in img.lower()]
                    if not real_images and primary_img and "placehold.co" not in primary_img.lower():
                        real_images.append(primary_img)

                    display_img = real_images[0] if real_images else primary_img

                    if display_img:
                        st.image(display_img, caption=f"{result.get('brand')} {result.get('manufacturer_part_number')}", use_container_width=True)
                        if "placehold.co" not in display_img.lower():
                            st.caption(f"[🔗 Direct Image Link]({display_img})")
                        else:
                            st.info("Showing a placeholder image. No direct product photo was found.")
                    else:
                        st.info("No product image found.")

                with col_info:
                    st.markdown(f"<span class='badge'>{result.get('category', 'Industrial Component')}</span>", unsafe_allow_html=True)
                    st.markdown(f"### {result.get('title')}")
                    conf = str(result.get("confidence", "medium")).lower()
                    conf_color = {"high": "🟢", "medium": "🟡", "low": "🟠"}.get(conf, "⚪")
                    st.markdown(f"**MPN:** `{result.get('manufacturer_part_number')}` &nbsp;|&nbsp; **Brand:** `{result.get('brand')}` &nbsp;|&nbsp; **Confidence:** {conf_color} {conf.title()}")
                    st.write(clean_desc)

                # Tabs for structured data
                tab_specs, tab_features, tab_norm, tab_evidence = st.tabs(
                    ["📊 Specifications", "✨ Key Features & Applications", "🏷️ Normalized Attributes", "🔍 Sources & Notes"]
                )

                with tab_specs:
                    st.markdown("#### Key Electrical & Mechanical Metrics")
                    specs = result.get("specifications", [])
                    norm_attrs = result.get("normalized_attributes", {})

                    source_labels = {
                        "extracted_spec": "Datasheet / Spec Text",
                        "input": "User Input Description",
                        "scraped": "Web Scraped",
                        "llm": "AI Inferred",
                        "inferred": "AI Inferred",
                        "normalized": "Catalog Normalized",
                    }

                    # real_specs / source_mentions were already computed above (and
                    # possibly AI-polished) before this tab renders.
                    filtered_count = max(0, len(specs) - len(real_specs) - len(source_mentions))

                    cleaned_specs = []
                    for spec in real_specs:
                        s_name = spec["name"]
                        s_val = spec["value"]
                        s_unit = spec["unit"]
                        raw_src = spec.get("source", "extracted_spec")

                        unit_display = str(s_unit).strip() if s_unit and str(s_unit).strip() not in ("None", "nan") else "-"
                        source_display = source_labels.get(raw_src, raw_src.replace("_", " ").title())

                        cleaned_specs.append({
                            "name": s_name,
                            "value": s_val,
                            "unit": unit_display,
                            "source": source_display,
                        })

                    if filtered_count > 0 or source_mentions:
                        st.caption(
                            f"ℹ️ {filtered_count + len(source_mentions)} low-value or duplicate entries "
                            f"were filtered out to keep this list clean and trustworthy."
                        )

                    card_keywords = [
                        "voltage", "current", "power", "frequency", "temperature",
                        "pressure", "speed", "weight", "diameter", "size", "thread",
                        "output", "enclosure", "sensing", "material", "rating"
                    ]

                    top_metrics = [s for s in cleaned_specs if any(k in s["name"].lower() for k in card_keywords)]

                    if top_metrics:
                        num_cards = min(len(top_metrics), 4)
                        metric_cols = st.columns(num_cards)
                        for idx, spec in enumerate(top_metrics[:num_cards]):
                            val_unit = f"{spec['value']} {spec['unit']}".replace(" -", "").strip()
                            with metric_cols[idx]:
                                st.metric(label=spec["name"], value=val_unit)
                    else:
                        st.caption("No headline key metrics detected for top summary cards.")

                    st.markdown("#### Complete Specifications Table")
                    if cleaned_specs:
                        df_specs = pd.DataFrame(cleaned_specs)
                        df_specs = df_specs.rename(columns={
                            "name": "Specification Name",
                            "value": "Value",
                            "unit": "Unit",
                            "source": "Source",
                        })
                        st.dataframe(
                            df_specs,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Specification Name": st.column_config.TextColumn("Specification Name", help="Name of parameter"),
                                "Value": st.column_config.TextColumn("Value"),
                                "Unit": st.column_config.TextColumn("Unit"),
                                "Source": st.column_config.TextColumn("Source"),
                            },
                        )
                    elif norm_attrs:
                        df_norm_specs = pd.DataFrame(
                            [
                                {
                                    "Specification Name": k.replace("_", " ").title(),
                                    "Value": str(v),
                                    "Unit": "-",
                                    "Source": "Catalog Normalized",
                                }
                                for k, v in norm_attrs.items()
                            ]
                        )
                        st.dataframe(df_norm_specs, use_container_width=True, hide_index=True)
                    else:
                        st.warning("No explicit numerical specifications detected in input/scraped text.")

                with tab_features:
                    col_feat, col_app = st.columns(2)
                    with col_feat:
                        st.markdown("#### Key Features")
                        if clean_feats:
                            for feat in clean_feats:
                                st.markdown(f"- {feat}")
                        else:
                            st.caption("No clean feature bullets were extracted for this product.")
                    with col_app:
                        st.markdown("#### Target Applications")
                        if clean_apps:
                            for app in clean_apps:
                                st.markdown(f"- 🛠️ {app}")
                        else:
                            st.caption("No target applications identified.")

                with tab_norm:
                    st.markdown("#### Normalized Catalog Attributes")
                    norm_attrs = dedupe_normalized_attributes(result.get("normalized_attributes", {}))
                    if norm_attrs:
                        df_norm = pd.DataFrame(
                            [{"Attribute Key": k, "Normalized Value": v} for k, v in norm_attrs.items()]
                        )
                        st.dataframe(df_norm, use_container_width=True, hide_index=True)
                    else:
                        st.info("No normalized key-value attributes available.")

                with tab_evidence:
                    st.markdown("#### Sources & Notes")
                    evidence = result.get("source_evidence", [])
                    if evidence:
                        df_ev = pd.DataFrame(evidence)
                        st.dataframe(df_ev, use_container_width=True, hide_index=True)
                    else:
                        st.caption("No source evidence recorded for this listing.")

                    if source_mentions:
                        with st.expander(f"📎 {len(source_mentions)} datasheet/brand references (filtered from specs)"):
                            st.caption(
                                "These were mentions of the datasheet or brand name picked up during scraping — "
                                "not real technical specifications — so they were kept here instead of the specs table."
                            )
                            st.dataframe(pd.DataFrame(source_mentions), use_container_width=True, hide_index=True)

                    if warnings := result.get("quality_warnings"):
                        st.markdown("##### Notes")
                        for warn in warnings:
                            st.warning(warn)

                st.download_button(
                    "📥 Download Listing (JSON)",
                    data=json.dumps(result, indent=2),
                    file_name=f"{mpn}.json",
                    mime="application/json",
                )
            elif response:
                try:
                    err = response.json()
                    st.error(f"**Error:** {err.get('detail', response.text)}")
                except Exception:
                    st.error(f"Request failed (HTTP {response.status_code}). Please try again.")


# ---------------------------------------------------------------------------
# TAB 2: UPLOAD PDF PRODUCT LIST (BOM / RFQ / CATALOG)
# ---------------------------------------------------------------------------
with main_tab2:
    st.subheader("📄 Upload a Product List (PDF)")
    st.markdown(
        "Upload a PDF containing a list of products — such as a bill of materials, purchase order, "
        "equipment list, RFQ, or catalog table — and the assistant will automatically pull out the part "
        "numbers, quantities, brands, and descriptions."
    )

    pdf_file = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        help="Upload a PDF containing part numbers, equipment lists, or bills of materials.",
    )

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        extract_button = st.button("🔍 Extract Products from PDF", use_container_width=True, disabled=pdf_file is None)
    with col_btn2:
        process_all_button = st.button("🚀 Extract & Enrich All Products", use_container_width=True, disabled=pdf_file is None)

    if pdf_file is not None and pdf_file.size > MAX_PDF_SIZE_MB * 1024 * 1024:
        st.error(f"This file is larger than {MAX_PDF_SIZE_MB}MB. Please upload a smaller PDF.")
        pdf_file = None

    if extract_button and pdf_file is not None:
        with st.spinner("📄 Reading the PDF and identifying products..."):
            try:
                files = {"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")}
                response = httpx.post(f"{API_URL}/upload-pdf-extract", files=files, timeout=120)
                if response.is_success:
                    extracted_data = response.json()
                    st.session_state["pdf_extracted_data"] = extracted_data
                    st.success(f"✅ Successfully parsed `{pdf_file.name}`! Found {extracted_data.get('total_products_found', 0)} products.")
                else:
                    st.error(f"Failed to extract PDF: {response.text}")
            except Exception as exc:
                st.error(f"Something went wrong connecting to the service: {exc}")

    if process_all_button and pdf_file is not None:
        with st.spinner("🤖 Extracting products and generating listings for each one..."):
            try:
                files = {"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")}
                response = httpx.post(f"{API_URL}/upload-pdf-process", files=files, timeout=600)
                if response.is_success:
                    batch_res = response.json()
                    st.session_state["pdf_batch_results"] = batch_res
                    st.success(f"🎉 Processed {batch_res.get('processed_count', 0)} of {batch_res.get('total_products_found', 0)} products from PDF!")
                else:
                    st.error(f"Failed batch processing: {response.text}")
            except Exception as exc:
                st.error(f"Something went wrong connecting to the service: {exc}")

    # Display Extracted Products Summary if available
    if "pdf_extracted_data" in st.session_state:
        ext = st.session_state["pdf_extracted_data"]
        prods = ext.get("products", [])
        st.markdown("---")
        st.markdown(f"### 📋 Extracted Product List from `{ext.get('filename')}`")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Products Found", ext.get("total_products_found", len(prods)))
        with m2:
            unique_brands = len(set(p.get("brand", "") for p in prods if p.get("brand")))
            st.metric("Unique Brands", unique_brands)
        with m3:
            total_units = sum(p.get("quantity") or 1 for p in prods)
            st.metric("Total Items / Quantity", total_units)

        if ext.get("warnings"):
            for w in ext["warnings"]:
                st.info(f"ℹ️ {w}")

        if prods:
            df_prods = pd.DataFrame(
                [
                    {
                        "Item #": idx + 1,
                        "Manufacturer Part Number (MPN)": p.get("manufacturer_part_number", ""),
                        "Brand / Manufacturer": p.get("brand", "Generic / Unspecified"),
                        "Quantity": p.get("quantity") or "-",
                        "Category": p.get("category") or "Industrial",
                        "Short Description": p.get("short_description", ""),
                    }
                    for idx, p in enumerate(prods)
                ]
            )
            st.dataframe(df_prods, use_container_width=True, hide_index=True)

            col_a, col_b = st.columns(2)
            with col_a:
                csv_data = df_prods.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download Extracted Product List (CSV)",
                    data=csv_data,
                    file_name=f"extracted_{ext.get('filename', 'products')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with col_b:
                st.download_button(
                    "📥 Download Extracted Product List (JSON)",
                    data=json.dumps(ext, indent=2),
                    file_name=f"extracted_{ext.get('filename', 'products')}.json",
                    mime="application/json",
                    use_container_width=True,
                )

    # Display Batch AI Enriched Results if available
    if "pdf_batch_results" in st.session_state:
        batch_data = st.session_state["pdf_batch_results"]
        results = batch_data.get("results", [])
        st.markdown("---")
        st.markdown(f"### 🚀 Generated Product Listings ({len(results)} Processed)")

        for idx, item in enumerate(results):
            with st.expander(
                f"**#{idx + 1}: {item.get('brand')} — {item.get('manufacturer_part_number')}** | {item.get('title')}",
                expanded=(idx == 0),
            ):
                c1, c2 = st.columns([1, 3])
                with c1:
                    img = item.get("image_url") or (item.get("images") and item.get("images")[0])
                    if img:
                        st.image(img, use_container_width=True)
                    st.caption(f"**Confidence:** `{item.get('confidence', 'medium')}`")
                    st.caption(f"**Category:** `{item.get('category')}`")
                with c2:
                    st.markdown(f"#### {item.get('title')}")
                    st.write(clean_description(item.get("commerce_description")))
                    item_feats = clean_features(item.get("key_features", []), max_items=3)
                    if item_feats:
                        st.markdown("**Key Features:**")
                        for feat in item_feats:
                            st.markdown(f"- {feat}")

                item_real_specs, _ = clean_specifications(item.get("specifications", []), item.get("brand", ""))
                if item_real_specs:
                    st.markdown("##### Specifications")
                    specs_df = pd.DataFrame(item_real_specs)[["name", "value", "unit"]].rename(
                        columns={"name": "Specification", "value": "Value", "unit": "Unit"}
                    )
                    st.dataframe(specs_df, use_container_width=True, hide_index=True)

        st.download_button(
            "📥 Download Complete Batch Results (JSON)",
            data=json.dumps(batch_data, indent=2),
            file_name=f"enriched_{batch_data.get('filename', 'batch')}.json",
            mime="application/json",
        )

st.markdown(
    '<div class="app-footer">Powered by Product Intelligence Assistant</div>',
    unsafe_allow_html=True,
)
