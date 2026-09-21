"""Turn reader and field-comparison evidence into an official BL decision."""

from collections.abc import Iterable, Mapping


REVIEW_REASONS = {
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
}

UNREADABLE_STATUSES = {"scanned", "unreadable", "empty"}


def _reader_statuses(reader_results):
    """Return status strings from result dictionaries or plain status names."""
    if reader_results is None:
        return []
    if isinstance(reader_results, Mapping):
        reader_results = reader_results.values()
    if not isinstance(reader_results, Iterable) or isinstance(reader_results, str):
        reader_results = [reader_results]

    statuses = []
    for result in reader_results:
        if isinstance(result, Mapping):
            statuses.append(result.get("status"))
        else:
            statuses.append(result)
    return [status for status in statuses if status]


def review_decision(reason, *, comparisons=None, warning=None):
    """Build a NEEDS_REVIEW result using one official review reason."""
    if reason not in REVIEW_REASONS:
        raise ValueError(f"Unsupported review reason: {reason}")

    result = {
        "status": "NEEDS_REVIEW",
        "review_reason": reason,
        "has_defect": False,
        "defect_fields": [],
        "comparisons": comparisons or [],
        "missing_fields": [],
        "uncertain_fields": [],
        "warnings": [],
    }
    if warning:
        result["warnings"].append(str(warning))
    return result


def decide_status(
    comparison=None,
    *,
    missing_attachment=False,
    wrong_doc_type=False,
    reader_results=None,
    llm_error=None,
):
    """Decide OK, MISMATCH, or NEEDS_REVIEW for one BL comparison.

    A definite mismatch takes precedence over uncertainty in another field:
    once at least one clear defect exists, the overall documents definitely do
    not match. Uncertain and missing fields remain visible for human follow-up.
    """
    if missing_attachment:
        return review_decision(
            "missing_attachment",
            warning="The Shipping Instruction or draft Bill of Lading is missing.",
        )
    if wrong_doc_type:
        return review_decision(
            "wrong_doc_type",
            warning="The attachments could not be identified as an SI and draft BL.",
        )

    statuses = _reader_statuses(reader_results)
    blocked_statuses = [status for status in statuses if status in UNREADABLE_STATUSES]
    if blocked_statuses:
        return review_decision(
            "unreadable",
            warning="One or more attachments could not be read reliably: "
            + ", ".join(blocked_statuses),
        )
    if llm_error is not None:
        return review_decision(
            "unreadable",
            warning=f"AI extraction failed after retries: {str(llm_error)[:200]}",
        )
    if not isinstance(comparison, Mapping):
        raise ValueError("comparison is required when the documents are readable")

    comparisons = list(comparison.get("comparisons", []))
    all_defects = list(comparison.get("defect_fields", []))
    missing_fields = list(comparison.get("missing_fields", []))
    uncertain_fields = list(comparison.get("uncertain_fields", []))
    clear_defects = [field for field in all_defects if field not in uncertain_fields]

    if clear_defects:
        warnings = []
        if missing_fields:
            warnings.append(
                "Some additional fields are missing: " + ", ".join(missing_fields)
            )
        if uncertain_fields:
            warnings.append(
                "Some additional fields require review: "
                + ", ".join(uncertain_fields)
            )
        return {
            "status": "MISMATCH",
            "review_reason": None,
            "has_defect": True,
            "defect_fields": clear_defects,
            "comparisons": comparisons,
            "missing_fields": missing_fields,
            "uncertain_fields": uncertain_fields,
            "warnings": warnings,
        }

    if missing_fields:
        result = review_decision(
            "missing_value",
            comparisons=comparisons,
            warning="Required fields are missing: " + ", ".join(missing_fields),
        )
        result["missing_fields"] = missing_fields
        result["uncertain_fields"] = uncertain_fields
        return result

    if uncertain_fields:
        result = review_decision(
            "unreadable",
            comparisons=comparisons,
            warning="Similar values require human review: "
            + ", ".join(uncertain_fields),
        )
        result["uncertain_fields"] = uncertain_fields
        return result

    return {
        "status": "OK",
        "review_reason": None,
        "has_defect": False,
        "defect_fields": [],
        "comparisons": comparisons,
        "missing_fields": [],
        "uncertain_fields": [],
        "warnings": [],
    }
