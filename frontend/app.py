"""Streamlit review interface for demo examples and the live local pipeline."""

import json
import os
from pathlib import Path

import streamlit as st

from backend.loader import Inbox
from backend.pipeline import process_email
from frontend.view_model import (
    comparison_label,
    display_value,
    evidence_caption,
    evidence_snippet,
    human_attention_label,
    ocr_documents,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = REPO_ROOT / "contracts" / "result_examples.json"
DEFAULT_DATASET = REPO_ROOT.parent / "Nash-project"

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
    "BL_COMPARISON": (
        "BL Comparison",
        "Compare the Shipping Instruction with the draft Bill of Lading.",
    ),
    "SI_REQUEST": (
        "Shipping Instruction Request",
        "Route this request to the shipping-document preparation workflow.",
    ),
    "INVOICE_QUERY": (
        "Invoice Query",
        "Route this email to the finance or billing team.",
    ),
    "GENERAL": ("General Email", "No SI/BL comparison is required."),
    "SPAM": ("Spam", "No document processing is required."),
}


@st.cache_data(show_spinner=False)
def load_demo_results():
    """Load stable examples so the UI can be demonstrated without Gemini."""
    with RESULTS_FILE.open(encoding="utf-8") as file:
        payload = json.load(file)
    return {example["email_id"]: example for example in payload["examples"]}


@st.cache_data(show_spinner=False)
def load_emails(source):
    """Load local inbox metadata without making any AI calls."""
    return Inbox(source).emails()


def dataset_is_valid(source):
    path = Path(source)
    return (path / "inbox").is_dir() and (path / "attachments").is_dir()


def gemini_key_is_configured():
    """Check configuration without displaying or transmitting the secret."""
    configured = os.getenv("GEMINI_API_KEY")
    if configured:
        return True
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "GEMINI_API_KEY":
            return bool(value.strip())
    return False


def show_status(result):
    status = result.get("status")
    if status == "OK":
        st.success("✅ OK — All seven required fields match.")
    elif status == "MISMATCH":
        st.error("❌ MISMATCH — Definite document differences were found.")
    elif status == "NEEDS_REVIEW":
        st.warning("⚠️ NEEDS REVIEW — This case needs a person to decide.")
    else:
        st.warning(f"Unknown verification status: {status}")


def show_category_result(result):
    category = result.get("category", "GENERAL")
    _label, message = CATEGORY_DETAILS.get(
        category,
        (category.replace("_", " ").title(), "Review this email."),
    )
    if category == "SPAM":
        st.warning(f"🚫 {message}")
    else:
        st.info(f"📨 {message}")


def show_ai_evidence(comparison):
    evidence_items = [
        ("Shipping Instruction", comparison.get("si_evidence")),
        ("Draft Bill of Lading", comparison.get("bl_evidence")),
    ]
    evidence_items = [(label, item) for label, item in evidence_items if item]
    if not evidence_items:
        return

    field_label = FIELD_LABELS.get(comparison["field"], comparison["field"])
    with st.expander(f"Source evidence · {field_label}"):
        for label, evidence in evidence_items:
            st.markdown(f"**{label}**")
            st.code(evidence_snippet(evidence) or "No excerpt available.", language=None)
            caption = evidence_caption(evidence, label)
            if caption:
                st.caption(caption)


def show_comparisons(result):
    comparisons = result.get("comparisons", [])
    if not comparisons:
        st.info("No field comparison is available for this case.")
        return

    rows = []
    for comparison in comparisons:
        confidence = comparison.get("confidence")
        rows.append(
            {
                "Field": FIELD_LABELS.get(comparison["field"], comparison["field"]),
                "Shipping Instruction": str(display_value(comparison.get("si_value"))),
                "Draft Bill of Lading": str(display_value(comparison.get("bl_value"))),
                "Result": comparison_label(comparison.get("match")),
                "Confidence": (
                    f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—"
                ),
            }
        )

    st.dataframe(rows, hide_index=True, width="stretch")

    for comparison in comparisons:
        if (
            comparison.get("match") is not True
            or comparison.get("si_evidence")
            or comparison.get("bl_evidence")
        ):
            show_ai_evidence(comparison)

    defect_fields = [
        FIELD_LABELS.get(field, field) for field in result.get("defect_fields", [])
    ]
    uncertain_fields = [
        FIELD_LABELS.get(field, field) for field in result.get("uncertain_fields", [])
    ]
    missing_fields = [
        FIELD_LABELS.get(field, field) for field in result.get("missing_fields", [])
    ]
    if defect_fields:
        st.error("Confirmed differences: " + ", ".join(defect_fields))
    if uncertain_fields:
        st.warning("Similar values requiring review: " + ", ".join(uncertain_fields))
    if missing_fields:
        st.warning("Missing required values: " + ", ".join(missing_fields))


def show_result(result):
    category = result.get("category", "GENERAL")
    category_label, _message = CATEGORY_DETAILS.get(
        category,
        (category.replace("_", " ").title(), "Review this email."),
    )

    st.divider()
    category_column, confidence_column, action_column = st.columns(3)
    category_column.metric("Email category", category_label)
    confidence_column.metric(
        "Classification confidence",
        f'{result.get("classification_confidence", 0):.0%}',
    )
    action_column.metric(
        "Next action",
        "Compare SI/BL" if category == "BL_COMPARISON" else "Route email",
    )

    reason = result.get("classification_reason")
    if reason:
        st.caption(f"AI classification reason: {reason}")

    st.subheader("Email details")
    email = result.get("email", {})
    detail_left, detail_right = st.columns(2)
    detail_left.write(f'**From:** {email.get("from", "Unknown sender")}')
    detail_right.write(f'**Subject:** {email.get("subject", "No subject")}')
    with st.expander("Email body", expanded=True):
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
        defect_column.metric(
            "Confirmed document defect", "Yes" if result.get("has_defect") else "No"
        )
        review_column.metric(
            "Human attention",
            human_attention_label(result),
        )
        used_ocr = ocr_documents(result)
        if used_ocr:
            st.info(
                "AI OCR read the "
                + " and ".join(used_ocr)
                + ". Page references are available, but a person should confirm critical values."
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


st.set_page_config(
    page_title="Nash Shipping Document Verifier",
    page_icon="📄",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1280px;}
      [data-testid="stMetric"] {background: rgba(120,120,120,.08); padding: 1rem; border-radius: .75rem;}
      [data-testid="stMetricValue"] {font-size: 1.65rem;}
      .stButton > button[kind="primary"] {
        background: #2563eb;
        border-color: #2563eb;
        color: white;
      }
      .stButton > button[kind="primary"]:hover {
        background: #1d4ed8;
        border-color: #1d4ed8;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📄 Shipping Document Verification")
st.caption("Team Nash · AI-assisted review with human oversight")

with st.sidebar:
    st.header("Run settings")
    mode = st.radio(
        "Data source",
        ["Demo examples", "Live local dataset"],
        help="Demo mode makes no Gemini calls. Live mode runs the real backend.",
    )
    use_ocr = True
    source = str(DEFAULT_DATASET)
    if mode == "Live local dataset":
        source = st.text_input("Dataset folder", value=source)
        use_ocr = st.toggle("Use Gemini OCR for scanned PDFs", value=True)
        st.caption("Live verification may consume Gemini API quota. Cached results are reused.")
        if gemini_key_is_configured():
            st.success("Gemini API key configured")
        else:
            st.warning("Add GEMINI_API_KEY to the repository .env file before running Live mode.")

if mode == "Demo examples":
    try:
        results = load_demo_results()
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        st.error(f"The demo results could not be loaded: {error}")
        st.stop()
    emails = {email_id: result.get("email", {}) for email_id, result in results.items()}
else:
    if not dataset_is_valid(source):
        st.error("Choose a dataset folder containing both `inbox/` and `attachments/`.")
        st.stop()
    try:
        records = load_emails(source)
    except (OSError, json.JSONDecodeError) as error:
        st.error(f"The inbox could not be loaded: {error}")
        st.stop()
    emails = {record["email_id"]: record for record in records}
    st.sidebar.success(f"{len(emails)} emails found")

st.write(
    "Select an email to classify it. BL comparison requests also show all seven "
    "SI/BL fields, differences, confidence, and source evidence."
)

email_id = st.selectbox(
    "Select an email",
    options=list(emails),
    format_func=lambda item: f'{item} — {emails[item].get("subject", "No subject")}',
)

run_clicked = st.button("🔍 Run verification", type="primary", width="stretch")
result_key = (mode, str(Path(source).resolve()), email_id, use_ocr)

if run_clicked:
    if mode == "Demo examples":
        st.session_state["last_verification"] = (result_key, results[email_id])
    else:
        with st.spinner("Reading documents and running AI verification…"):
            try:
                result = process_email(emails[email_id], source, use_ocr=use_ocr)
            except Exception as error:
                st.error(f"Verification failed: {type(error).__name__}: {error}")
            else:
                st.session_state["last_verification"] = (result_key, result)

last_verification = st.session_state.get("last_verification")
if last_verification and last_verification[0] == result_key:
    show_result(last_verification[1])
