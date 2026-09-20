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

CATEGORY_DETAILS = {
    "BL_COMPARISON": {
        "label": "BL Comparison",
        "message": "Compare the Shipping Instruction with the draft Bill of Lading.",
    },
    "SI_REQUEST": {
        "label": "Shipping Instruction Request",
        "message": "This email requests a Shipping Instruction. Document comparison is not required.",
    },
    "INVOICE_QUERY": {
        "label": "Invoice Query",
        "message": "This email concerns an invoice. Document comparison is not required.",
    },
    "GENERAL": {
        "label": "General Email",
        "message": "This is a general enquiry. Document comparison is not required.",
    },
    "SPAM": {
        "label": "Spam",
        "message": "This email was classified as spam. No document processing is required.",
    },
}


@st.cache_data
def load_results():
    """Load the shared frontend-backend result examples."""
    with RESULTS_FILE.open(encoding="utf-8") as file:
        payload = json.load(file)
    return {example["email_id"]: example for example in payload["examples"]}


def get_result(email_id, results):
    """Return one result through the frontend-backend boundary.

    During UI development this reads the shared JSON examples. When the backend is
    ready, only this function needs to call its process_email(email_id) function.
    """
    return results[email_id]


def show_status(result):
    """Display the overall verification outcome with a clear colour."""
    status = result["status"]
    if status == "OK":
        st.success("✅ OK — The Shipping Instruction and draft Bill of Lading match.")
    elif status == "MISMATCH":
        st.error("❌ MISMATCH — Differences were found between the documents.")
    elif status == "NEEDS_REVIEW":
        st.warning("⚠️ NEEDS REVIEW — A person needs to review this case.")
    else:
        st.warning(f"Unknown verification status: {status}")


def show_category_result(result):
    """Explain how the classified email should be handled."""
    category = result.get("category", "GENERAL")
    details = CATEGORY_DETAILS.get(
        category,
        {"label": category.replace("_", " ").title(), "message": "Review this email."},
    )

    if category == "SPAM":
        st.warning(f'🚫 {details["message"]}')
    else:
        st.info(f'📨 {details["message"]}')


def evidence_caption(evidence):
    """Build a short, readable source reference for an AI evidence snippet."""
    source = evidence.get("source")
    page = evidence.get("page")
    if source and page is not None:
        return f"Source: {source}, page {page}"
    if source:
        return f"Source: {source}"
    return None


def show_ai_evidence(comparison):
    """Show optional source snippets without exposing model chain-of-thought."""
    evidence_items = [
        ("Shipping Instruction evidence", comparison.get("si_evidence")),
        ("Draft Bill of Lading evidence", comparison.get("bl_evidence")),
    ]
    evidence_items = [(label, item) for label, item in evidence_items if item]
    if not evidence_items:
        return

    field_label = FIELD_LABELS.get(comparison["field"], comparison["field"])
    with st.expander(f"AI source evidence · {field_label}"):
        for label, evidence in evidence_items:
            st.markdown(f"**{label}**")
            st.code(evidence.get("text", "No excerpt available."), language=None)
            caption = evidence_caption(evidence)
            if caption:
                st.caption(caption)


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

    for comparison in comparisons:
        if not comparison.get("match", False) or comparison.get("si_evidence") or comparison.get("bl_evidence"):
            show_ai_evidence(comparison)

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
    "Select an email to review its AI classification. BL comparison requests "
    "also show the Shipping Instruction and draft Bill of Lading differences."
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
    result = get_result(email_id, results)
    category = result.get("category", "GENERAL")
    category_details = CATEGORY_DETAILS.get(
        category,
        {"label": category.replace("_", " ").title()},
    )

    st.divider()
    category_column, confidence_column, action_column = st.columns(3)
    category_column.metric("Email category", category_details["label"])
    confidence_column.metric(
        "Classification confidence",
        f'{result.get("classification_confidence", 0):.0%}',
    )
    action_column.metric(
        "Next action",
        "Compare documents" if category == "BL_COMPARISON" else "Route email",
    )

    st.subheader("Email details")
    email = result.get("email", {})
    st.write(f'**From:** {email.get("from", "Unknown sender")}')
    st.write(f'**Subject:** {email.get("subject", "No subject")}')
    st.write(email.get("body", "No email body available."))

    with st.expander("Attachments"):
        attachments = email.get("attachments", [])
        if attachments:
            for attachment in attachments:
                st.write(f"• {attachment}")
        else:
            st.write("No attachments.")

    if category == "BL_COMPARISON":
        show_status(result)
        defect_column, review_column = st.columns(2)
        defect_column.metric("Document defect", "Yes" if result.get("has_defect") else "No")
        review_column.metric(
            "Human attention",
            "Required" if result.get("status") != "OK" else "Not required",
        )

        st.subheader("SI and draft BL comparison")
        show_comparisons(result)
    else:
        show_category_result(result)

    for warning in result.get("warnings", []):
        st.warning(warning)

    if result.get("review_reason"):
        readable_reason = result["review_reason"].replace("_", " ").title()
        st.info(f"Review reason: {readable_reason}")
