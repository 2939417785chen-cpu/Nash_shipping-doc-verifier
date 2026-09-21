"""Pure formatting helpers shared by the Streamlit review interface."""


def display_value(value):
    """Keep zero meaningful while making missing values obvious."""
    return "—" if value is None or value == "" else value


def comparison_label(match):
    if match is True:
        return "✅ Match"
    if match is False:
        return "❌ Mismatch"
    return "⚠️ Needs review"


def ocr_documents(result):
    """Return document labels successfully read from images."""
    readings = result.get("document_reading", {}) if isinstance(result, dict) else {}
    return [
        document_type
        for document_type, reading in readings.items()
        if isinstance(reading, dict) and reading.get("status") == "ok" and reading.get("ocr")
    ]


def human_attention_label(result):
    if result.get("status") != "OK":
        return "Required"
    if ocr_documents(result):
        return "Recommended"
    return "Not required"


def evidence_snippet(evidence):
    """Accept both the live backend schema and the older demo schema."""
    if not isinstance(evidence, dict):
        return str(evidence or "")
    return str(evidence.get("snippet") or evidence.get("text") or "")


def evidence_caption(evidence, document_label=None):
    """Describe source, page, and verification without overstating certainty."""
    if not isinstance(evidence, dict):
        return None
    source = evidence.get("source") or document_label
    page = evidence.get("page")
    parts = []
    if source:
        parts.append(str(source))
    if page is not None:
        parts.append(f"page {page}")

    verified = evidence.get("verified")
    page_source = evidence.get("page_source")
    if verified is True:
        parts.append("snippet verified")
    elif page_source == "value":
        parts.append("page located from extracted value; snippet not exact")
    elif verified is False:
        parts.append("snippet not verified")
    return " · ".join(parts) or None
