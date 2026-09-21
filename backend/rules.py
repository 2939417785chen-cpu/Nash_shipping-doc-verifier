"""Small rules that need no AI.

They decide things that must come out the same way every time, or that the AI
gets wrong. They are plain functions, so they are free to run and easy to test.
"""
import re

# ---------------------------------------------------------------------------
# 1. Emails that only ask for the draft BL to be sent ("Please send the draft BL
#    for X for checking"). Nothing is attached and nothing is expected to be:
#    it is a document-check request, but there is nothing to compare yet.
# ---------------------------------------------------------------------------
_DRAFT_REQUEST = re.compile(
    r"\bsend\s+(?:us\s+|me\s+)?the\s+draft\s+(?:BL|B/L|bill\s+of\s+lading)\b", re.I)


def is_draft_bl_request(email):
    """True for an email without attachments that asks for the draft BL to be sent."""
    return not email.get("attachments") and bool(_DRAFT_REQUEST.search(email.get("body") or ""))


# ---------------------------------------------------------------------------
# 2. What kind of document is this? Look at its title, not at its file name.
# ---------------------------------------------------------------------------
DOCUMENT_TITLES = {
    "SI": ("SHIPPING INSTRUCTION", "BILL OF LADING INSTRUCTION"),  # the PDF template calls the SI this
    "BL": ("BILL OF LADING",),
    "PACKING_LIST": ("PACKING LIST",),
    "COMMERCIAL_INVOICE": ("COMMERCIAL INVOICE",),
    "CERTIFICATE_OF_ORIGIN": ("CERTIFICATE OF ORIGIN",),
}


def document_kind(text, lines=3):
    """The kind of document, from the first few lines (None if there is no clear title)."""
    head = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("##"):  # "## Sheet: ..." lines come from Excel files
            head.append(line.upper())
        if len(head) == lines:
            break
    joined = " | ".join(head)
    for kind, titles in DOCUMENT_TITLES.items():
        if any(title in joined for title in titles):
            return kind
    return None


def is_wrong_document(expected, text):
    """expected is "SI" or "BL". True when the text is clearly another kind of document."""
    kind = document_kind(text)
    return kind is not None and kind != expected


# ---------------------------------------------------------------------------
# 3. Required fields that are blank or a placeholder (N/A, ____, TBA ...).
# ---------------------------------------------------------------------------
REQUIRED_LABELS = {
    "shipper": r"shipper|exporter",
    "consignee": r"consignee|to the order",
    "notify_party": r"notify",
    "port_of_loading": r"port of loading|\bpol\b|load port",
    "port_of_discharge": r"port of discharge|\bpod\b|discharge port",
    "container_count": r"containers?",
    "gross_weight_kg": r"gross\s*w",
}
_LABEL_VALUE = re.compile(r"^(.*?)(?:\s*[:\t]\s*|\s+\|\s+)(.*)$")
_BLANK_VALUE = re.compile(
    r"^(?:N/?A|NIL|NONE|TBA|TBC|TO\s+BE\s+(?:ADVISED|CONFIRMED)|-+|_{2,}|\.{3,})"
    r"\s*(?:MTS?|KGS?|CBM)?$", re.I)


def blank_required_fields(text):
    """Names of required fields whose line has a label but no real value."""
    found = []
    for line in (text or "").splitlines():
        match = _LABEL_VALUE.match(line.strip())
        if not match:
            continue
        label, value = match.group(1).lower(), match.group(2).strip()
        for field, pattern in REQUIRED_LABELS.items():
            if field not in found and re.search(pattern, label) and (not value or _BLANK_VALUE.match(value)):
                found.append(field)
    return found