import json
import httpx
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Product Intelligence Agent", layout="wide")
st.title("Industrial Commerce Product AI Agent")

with st.form("single_product"):
    mpn = st.text_input("Manufacturer part number")
    brand = st.text_input("Brand")
    desc = st.text_area("Short description")
    urls = st.text_area("Supporting URLs, one per line")
    supporting_text = st.text_area("Supporting catalog/spec text")
    submitted = st.form_submit_button("Process product")

if submitted:
    payload = {
        "manufacturer_part_number": mpn,
        "brand": brand,
        "short_description": desc,
        "supporting_urls": [line.strip() for line in urls.splitlines() if line.strip()],
        "supporting_text": supporting_text or None,
    }
    with st.spinner("Building product intelligence..."):
        response = httpx.post(f"{API_URL}/process-product", json=payload, timeout=60)
    if response.is_success:
        result = response.json()
        st.subheader(result["title"])
        st.write(result["commerce_description"])
        left, right = st.columns(2)
        with left:
            st.markdown("#### Key features")
            for item in result["key_features"]:
                st.write(f"- {item}")
            st.markdown("#### Specifications")
            st.dataframe(result["specifications"], use_container_width=True)
        with right:
            st.markdown("#### Traceability")
            st.dataframe(result["source_evidence"], use_container_width=True)
            st.markdown("#### Quality warnings")
            for warning in result["quality_warnings"]:
                st.warning(warning)
        st.download_button("Download JSON", json.dumps(result, indent=2), file_name=f"{mpn or 'product'}.json")
    else:
        st.error(response.text)
