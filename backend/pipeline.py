"""End-to-end orchestration for email classification and SI/BL verification."""

import inspect
from pathlib import Path

from backend import compare, rules
from backend.decision import decide_status, review_decision
from backend.evidence import enrich_field_evidence
from backend.loader import Inbox
from backend.result_validator import assert_valid_result
from backend.submission import load_expected_email_ids, write_submission


class PipelineRunError(RuntimeError):
    """Raised when a complete submission cannot be produced safely."""


# True: a document that was read from a picture by AI vision (OCR) always goes to a person.
OCR_NEEDS_REVIEW = True

DRAFT_REQUEST_REASON = (
    "Rule: the sender asks for the draft BL to be sent and nothing is attached, "
    "so this is a document-check request with nothing to compare yet."
)
DRAFT_REQUEST_WARNING = (
    "The sender asks for the draft BL to be sent. No documents were attached, "
    "so there is nothing to compare yet."
)
_ROLE_NAMES = {"SI": "Shipping Instruction", "BL": "draft Bill of Lading"}
_KIND_NAMES = {
    "SI": "Shipping Instruction",
    "BL": "Bill of Lading",
    "PACKING_LIST": "Packing List",
    "COMMERCIAL_INVOICE": "Commercial Invoice",
    "CERTIFICATE_OF_ORIGIN": "Certificate of Origin",
}


def identify_document_attachments(attachments):
    """Find one SI and one BL using the official bundle filename convention."""
    si_paths = []
    bl_paths = []
    for attachment in attachments or []:
        name = Path(attachment).name.upper()
        if "_SI." in name:
            si_paths.append(attachment)
        elif "_BL." in name:
            bl_paths.append(attachment)

    return {
        "si": si_paths[0] if len(si_paths) == 1 else None,
        "bl": bl_paths[0] if len(bl_paths) == 1 else None,
        "missing_attachment": not si_paths or not bl_paths,
        "wrong_doc_type": len(si_paths) > 1 or len(bl_paths) > 1,
    }


def _base_result(email, classification):
    """Create the metadata shared by comparison and routing results."""
    return {
        "email_id": email["email_id"],
        "email": {
            "from": email.get("from", ""),
            "subject": email.get("subject", ""),
            "body": email.get("body", ""),
            "attachments": list(email.get("attachments", [])),
        },
        "category": classification["category"],
        "classification_confidence": classification.get("confidence", 0.0),
        "classification_reason": classification.get("reason", ""),
    }


def _routing_result(base_result):
    """Build a valid official result for a non-BL email category."""
    return {
        **base_result,
        "status": "OK",
        "review_reason": None,
        "has_defect": False,
        "defect_fields": [],
        "comparisons": [],
        "warnings": [],
    }


def _read_document(read_fn, path, use_ocr):
    """Use the OCR option when supported, while remaining compatible with main."""
    if "ocr" in inspect.signature(read_fn).parameters:
        return read_fn(path, ocr=use_ocr)
    return read_fn(path)


def _attach_reading_metadata(result, read_results):
    """Expose reader/OCR provenance to the review UI without changing scoring."""
    result["document_reading"] = {
        document_type: {
            "status": reading.get("status"),
            "ocr": bool(reading.get("ocr")),
            "pages": len(reading.get("pages") or []),
            "note": reading.get("note", ""),
        }
        for document_type, reading in read_results.items()
    }
    ocr_documents = [
        document_type
        for document_type, reading in read_results.items()
        if reading.get("status") == "ok" and reading.get("ocr")
    ]
    if ocr_documents:
        result.setdefault("warnings", []).append(
            "AI OCR was used for "
            + " and ".join(ocr_documents)
            + "; verify the source evidence because image transcription may contain small errors."
        )
    return result


def process_email(
    email,
    source,
    *,
    use_ocr=True,
    classify_fn=None,
    extract_fn=None,
    read_fn=None,
    compare_fn=None,
    llm_error_type=None,
):
    """Process one local-bundle email and return a validated rich result."""
    llm_module = None
    if classify_fn is None:
        from backend import llm as llm_module

    classify_fn = classify_fn or llm_module.classify_email
    compare_fn = compare_fn or compare.compare_fields
    llm_error_type = llm_error_type or (
        llm_module.LLMError if llm_module is not None else Exception
    )

    if rules.is_draft_bl_request(email):
        classification = {
            "category": "BL_COMPARISON",
            "confidence": 0.95,
            "reason": DRAFT_REQUEST_REASON,
        }
        result = _routing_result(_base_result(email, classification))
        result["warnings"].append(DRAFT_REQUEST_WARNING)
        assert_valid_result(result)
        return result

    try:
        classification = classify_fn(email)
    except llm_error_type as error:
        # The official schema has no UNKNOWN category and only BL_COMPARISON
        # supports NEEDS_REVIEW. Preserve a complete, reviewable result instead
        # of dropping the email when every configured model is unavailable.
        classification = {
            "category": "BL_COMPARISON",
            "confidence": 0.0,
            "reason": "AI classification was unavailable; category is a safe review fallback.",
        }
        base_result = _base_result(email, classification)
        decision = decide_status(llm_error=error)
        result = {**base_result, **decision}
        result["warnings"].append(
            "Email classification could not be completed; BL_COMPARISON is a safe fallback for human review."
        )
        assert_valid_result(result)
        return result

    base_result = _base_result(email, classification)
    if classification["category"] != "BL_COMPARISON":
        result = _routing_result(base_result)
        assert_valid_result(result)
        return result

    documents = identify_document_attachments(email.get("attachments", []))
    if documents["wrong_doc_type"] or documents["missing_attachment"]:
        decision = decide_status(
            wrong_doc_type=documents["wrong_doc_type"],
            missing_attachment=documents["missing_attachment"],
        )
        result = {**base_result, **decision}
        assert_valid_result(result)
        return result

    if read_fn is None:
        from backend import readers

        read_fn = readers.read_attachment

    source_path = Path(source)
    read_results = {
        "SI": _read_document(read_fn, source_path / documents["si"], use_ocr),
        "BL": _read_document(read_fn, source_path / documents["bl"], use_ocr),
    }
    if any(item.get("status") != "ok" for item in read_results.values()):
        decision = decide_status(reader_results=read_results)
        result = {**base_result, **decision}
        _attach_reading_metadata(result, read_results)
        assert_valid_result(result)
        return result

    wrong_kinds = {
        role: rules.document_kind(read_results[role]["text"])
        for role in ("SI", "BL")
        if rules.is_wrong_document(role, read_results[role]["text"])
    }
    if wrong_kinds:
        decision = decide_status(wrong_doc_type=True)
        decision["warnings"] = [
            f"The {role} attachment looks like a {_KIND_NAMES.get(kind, kind)}, "
            f"not a {_ROLE_NAMES[role]}."
            for role, kind in wrong_kinds.items()
        ]
        result = {**base_result, **decision}
        _attach_reading_metadata(result, read_results)
        assert_valid_result(result)
        return result

    blank_fields = {
        role: rules.blank_required_fields(read_results[role]["text"])
        for role in ("SI", "BL")
    }
    if any(blank_fields.values()):
        missing = [
            field
            for field in compare.FIELDS
            if any(field in fields for fields in blank_fields.values())
        ]
        details = "; ".join(
            f"{role}: {', '.join(fields)}" for role, fields in blank_fields.items() if fields
        )
        decision = review_decision(
            "missing_value",
            warning=f"Required fields are blank or contain a placeholder ({details}).",
        )
        decision["missing_fields"] = missing
        result = {**base_result, **decision}
        _attach_reading_metadata(result, read_results)
        assert_valid_result(result)
        return result

    if extract_fn is None:
        if llm_module is None:
            from backend import llm as llm_module
        extract_fn = llm_module.extract_fields
    try:
        si_fields = extract_fn(read_results["SI"]["text"], "SI")
        bl_fields = extract_fn(read_results["BL"]["text"], "BL")
        si_fields = enrich_field_evidence(si_fields, read_results["SI"])
        bl_fields = enrich_field_evidence(bl_fields, read_results["BL"])
    except llm_error_type as error:
        decision = decide_status(llm_error=error)
    else:
        comparison = compare_fn(si_fields, bl_fields)
        if not any(item.get("ocr") for item in read_results.values()):
            # Both documents were read as text, so two values that differ are really
            # different. "Look-alike, please check" only makes sense when a picture was read.
            comparison = {**comparison, "uncertain_fields": []}
        decision = decide_status(comparison)
        
        if OCR_NEEDS_REVIEW and any(item.get("ocr") for item in read_results.values()):
            decision = review_decision(
                "unreadable",
                comparisons=list(comparison.get("comparisons", [])),
                warning=(
                    "One or more documents were read from a picture by AI vision (OCR). "
                    "A person should confirm the values before this result is final."
                ),
            )
            decision["missing_fields"] = list(comparison.get("missing_fields", []))
            decision["uncertain_fields"] = list(comparison.get("uncertain_fields", []))

    result = {**base_result, **decision}
    _attach_reading_metadata(result, read_results)
    assert_valid_result(result)
    return result


def run_pipeline(source, *, emails=None, process_fn=None, **process_options):
    """Process a complete inbox while collecting per-email failures."""
    process_fn = process_fn or process_email
    if emails is None:
        emails = Inbox(str(source)).emails()

    results = {}
    errors = {}
    for email in emails:
        email_id = email.get("email_id", "<missing email_id>")
        try:
            results[email_id] = process_fn(
                email,
                source,
                **process_options,
            )
        except Exception as error:  # one bad email must not stop the other 519
            errors[email_id] = f"{type(error).__name__}: {str(error)[:300]}"
    return results, errors


def run_and_write_submission(
    source,
    output_path,
    sample_submission_path,
    **process_options,
):
    """Run every email and write a submission only when nothing failed."""
    results, errors = run_pipeline(source, **process_options)
    if errors:
        preview = "; ".join(
            f"{email_id}: {message}" for email_id, message in list(errors.items())[:5]
        )
        raise PipelineRunError(
            f"{len(errors)} emails failed; submission was not written. {preview}"
        )

    expected_ids = load_expected_email_ids(sample_submission_path)
    return write_submission(results, output_path, expected_ids)