import json
import httpx
import pandas as pd
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Industrial Product AI Agent",
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
        margin-bottom: 0.5rem;
    }
    .sub-title {
        color: #475569;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .product-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
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
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">Industrial Commerce Product AI Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Extract, enrich, scrape, and structure product intelligence for commerce catalogs</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Configuration")
    api_url_input = st.text_input("FastAPI Service URL", API_URL)
    st.markdown("---")
    st.markdown("### Quick Examples")
    if st.button("Sample 1: Proximity Sensor"):
        st.session_state["mpn"] = "XS618B1PAL2"
        st.session_state["brand"] = "Schneider Electric"
        st.session_state["desc"] = "Inductive proximity sensor 18mm 24VDC PNP NO"
    if st.button("Sample 2: Industrial Motor"):
        st.session_state["mpn"] = "1LA7096-4AA10"
        st.session_state["brand"] = "Siemens"
        st.session_state["desc"] = "3-phase asynchronous motor 1.5 kW 230/400V 1420 RPM"

with st.form("single_product"):
    st.subheader("📦 Product Query Input")
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
        "🌐 Product Page / Website URL (Agent will automatically extract product photo & specs from website)",
        placeholder="https://www.example.com/product/XS618B1PAL2",
        help="Paste any manufacturer or distributor product URL. The AI Agent will automatically extract product images and datasheets.",
    )

    with st.expander("📄 Additional Supporting Materials (Extra URLs & Spec Text)", expanded=False):
        urls = st.text_area("Additional Product URLs (one per line)", placeholder="https://example.com/datasheet.pdf")
        supporting_text = st.text_area(
            "Raw Spec / Catalog Text",
            placeholder="Paste raw spec sheets, user manuals, or catalog copy here...",
            height=100,
        )

    submitted = st.form_submit_button("🚀 Process & Generate Intelligence", use_container_width=True)

if submitted:
    if not mpn or not brand or not desc:
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
        with st.spinner("🤖 Searching web, scraping datasheets, and running AI Gateway reasoning..."):
            try:
                target_url = api_url_input.rstrip("/")
                response = httpx.post(f"{target_url}/process-product", json=payload, timeout=300)
            except Exception as exc:
                st.error(f"Failed to connect to backend API at `{api_url_input}`: {exc}")
                response = None

        if response and response.is_success:
            result = response.json()
            st.success("✅ Product Intelligence Generated Successfully!")

            # Top Overview Header
            st.markdown("---")
            col_img, col_info = st.columns([1, 2])

            with col_img:
                st.markdown("#### 🖼️ Product Image")
                all_images = result.get("images", [])
                primary_img = result.get("image_url")

                # Filter out placeholders if real web images exist
                real_images = [img for img in all_images if "placehold.co" not in img.lower()]
                if not real_images and primary_img and "placehold.co" not in primary_img.lower():
                    real_images.append(primary_img)

                display_img = real_images[0] if real_images else primary_img

                if display_img:
                    st.image(display_img, caption=f"{result.get('brand')} {result.get('manufacturer_part_number')}", use_container_width=True)
                    if "placehold.co" not in display_img.lower():
                        st.caption(f"[🔗 Direct Image Link]({display_img})")
                    else:
                        st.info("Showing generated placeholder. No direct web photo found.")
                else:
                    st.info("No web image extracted.")

            with col_info:
                st.markdown(f"<span class='badge'>{result.get('category', 'Industrial Component')}</span>", unsafe_allow_html=True)
                st.markdown(f"### {result.get('title')}")
                st.markdown(f"**MPN:** `{result.get('manufacturer_part_number')}` &nbsp;|&nbsp; **Brand:** `{result.get('brand')}` &nbsp;|&nbsp; **Confidence:** `{result.get('confidence', 'medium')}`")
                st.write(result.get("commerce_description"))

            # Tabs for structured data
            tab_specs, tab_features, tab_norm, tab_evidence = st.tabs(
                ["📊 Specifications", "✨ Key Features & Apps", "🏷️ Normalized Attributes", "🔍 Traceability & Evidence"]
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

                cleaned_specs = []
                for spec in specs:
                    s_name = spec.get("name", "").strip() if isinstance(spec, dict) else getattr(spec, "name", "").strip()
                    s_val = str(spec.get("value", "") if isinstance(spec, dict) else getattr(spec, "value", "")).strip()
                    s_unit = spec.get("unit") if isinstance(spec, dict) else getattr(spec, "unit", None)
                    raw_src = (spec.get("source") if isinstance(spec, dict) else getattr(spec, "source", None)) or "extracted_spec"

                    if not s_name or not s_val:
                        continue

                    unit_display = str(s_unit).strip() if s_unit and str(s_unit).strip() not in ("None", "nan") else "-"
                    source_display = source_labels.get(raw_src, raw_src.replace("_", " ").title())

                    cleaned_specs.append({
                        "name": s_name,
                        "value": s_val,
                        "unit": unit_display,
                        "source": source_display,
                    })

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
                    for feat in result.get("key_features", []):
                        st.markdown(f"- {feat}")
                with col_app:
                    st.markdown("#### Target Applications")
                    for app in result.get("applications", []):
                        st.markdown(f"- 🛠️ {app}")

            with tab_norm:
                st.markdown("#### Normalized Catalog Attributes")
                norm_attrs = result.get("normalized_attributes", {})
                if norm_attrs:
                    df_norm = pd.DataFrame(
                        [{"Attribute Key": k, "Normalized Value": v} for k, v in norm_attrs.items()]
                    )
                    st.dataframe(df_norm, use_container_width=True, hide_index=True)
                else:
                    st.info("No normalized key-value attributes available.")

            with tab_evidence:
                st.markdown("#### Evidence & Warnings")
                evidence = result.get("source_evidence", [])
                if evidence:
                    df_ev = pd.DataFrame(evidence)
                    st.dataframe(df_ev, use_container_width=True, hide_index=True)
                if warnings := result.get("quality_warnings"):
                    st.markdown("##### Quality Warnings")
                    for warn in warnings:
                        st.warning(warn)

            # Additional Image Gallery if multiple images extracted
            gallery_images = real_images if 'real_images' in locals() and real_images else [img for img in result.get("images", []) if "placehold.co" not in img.lower()]
            if gallery_images and len(gallery_images) > 1:
                st.markdown("#### 📸 Additional Extracted Product Images")
                cols = st.columns(min(len(gallery_images), 4))
                for idx, img in enumerate(gallery_images[:4]):
                    with cols[idx]:
                        st.image(img, use_container_width=True)

            st.download_button(
                "📥 Download Product Intelligence JSON",
                data=json.dumps(result, indent=2),
                file_name=f"{mpn}.json",
                mime="application/json",
            )
        elif response:
            try:
                err = response.json()
                st.error(f"**HTTP {response.status_code} Error:** {err.get('detail', response.text)}")
            except Exception:
                st.error(f"HTTP {response.status_code}: {response.text}")
