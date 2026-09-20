import json
from pathlib import Path

import streamlit as st


RESULTS_FILE = (
    Path(__file__).resolve().parent.parent / "contracts" / "result_examples.json"
)

FIELD_LABELS = {
    "shipper": "Shipper",
    "consignee": "Consignee",
    "notify_party": "Notify Party",
    "port_of_loading": "Port of Loading",
    "port_of_discharge": "Port of Discharge",
    "container_count": "Container Count",
    "gross_weight_kg": "Gross Weight (kg)",
}


@st.cache_data
def load_results():
    """Load the shared frontend-backend result examples."""
    with RESULTS_FILE.open(encoding="utf-8") as file:
        payload = json.load(file)
    return {example["email_id"]: example for example in payload["examples"]}


def show_status(result):
    """Display the overall verification outcome with a clear colour."""
    status = result["status"]
    if status == "OK":
        st.success("✅ OK — The Shipping Instruction and draft Bill of Lading match.")
    elif status == "MISMATCH":
        st.error("❌ MISMATCH — Differences were found between the documents.")
    else:
        st.warning("⚠️ NEEDS REVIEW — A person needs to review this case.")


def show_comparisons(result):
    """Display all available SI/BL field comparisons."""
    comparisons = result.get("comparisons", [])
    if not comparisons:
        st.info("No field comparison is available for this case.")
        return

    rows = []
    for comparison in comparisons:
        rows.append(
            {
                "Field": FIELD_LABELS.get(comparison["field"], comparison["field"]),
                "Shipping Instruction": comparison["si_value"],
                "Draft Bill of Lading": comparison["bl_value"],
                "Result": "✅ Match" if comparison["match"] else "❌ Mismatch",
                "Confidence": f'{comparison["confidence"]:.0%}',
            }
        )

    st.dataframe(rows, hide_index=True, use_container_width=True)

    mismatched_fields = [
        FIELD_LABELS.get(field, field) for field in result.get("defect_fields", [])
    ]
    if mismatched_fields:
        st.error("Fields requiring attention: " + ", ".join(mismatched_fields))


st.set_page_config(
    page_title="Nash Shipping Document Verifier",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Shipping Document Verification")
st.caption("Team Nash · AI-assisted review with human oversight")

st.write(
    "Select an email to review its classification and compare the Shipping "
    "Instruction with the draft Bill of Lading."
)

try:
    results = load_results()
except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
    st.error(f"The verification results could not be loaded: {error}")
    st.stop()

email_id = st.selectbox(
    "Select an email",
    options=list(results),
    format_func=lambda item: f'{item} — {results[item]["email"]["subject"]}',
)

if st.button("🔍 Run verification", type="primary"):
    result = results[email_id]

    st.divider()
    show_status(result)

    category_column, confidence_column, defect_column = st.columns(3)
    category_column.metric("Email category", result["category"].replace("_", " "))
    confidence_column.metric(
        "Classification confidence", f'{result["classification_confidence"]:.0%}'
    )
    defect_column.metric("Document defect", "Yes" if result["has_defect"] else "No")

    st.subheader("Email details")
    st.write(f'**From:** {result["email"]["from"]}')
    st.write(f'**Subject:** {result["email"]["subject"]}')
    st.write(result["email"]["body"])

    with st.expander("Attachments"):
        for attachment in result["email"].get("attachments", []):
            st.write(f"• {attachment}")

    st.subheader("SI and draft BL comparison")
    show_comparisons(result)

    for warning in result.get("warnings", []):
        st.warning(warning)

    if result.get("review_reason"):
        readable_reason = result["review_reason"].replace("_", " ").title()
        st.info(f"Review reason: {readable_reason}")
