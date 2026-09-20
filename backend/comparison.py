"""Deterministic comparison and status decisions for extracted SI/BL fields."""

from collections.abc import Mapping

from backend.normalizer import is_missing, normalize_value


COMPARISON_FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

REVIEW_REASONS = {
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
}


def review_result(reason, comparisons=None):
    """Build a valid NEEDS_REVIEW result for an undecidable case."""
    if reason not in REVIEW_REASONS:
        raise ValueError(f"Unsupported review reason: {reason}")

    return {
        "status": "NEEDS_REVIEW",
        "review_reason": reason,
        "has_defect": False,
        "defect_fields": [],
        "comparisons": comparisons or [],
    }


def compare_documents(si_fields, bl_fields, field_confidences=None):
    """Compare the seven official fields extracted from an SI and draft BL.

    Passing None for either document represents a missing attachment. Missing
    or unparseable field values produce NEEDS_REVIEW rather than a mismatch,
    because the available evidence is insufficient to decide.
    """
    if si_fields is None or bl_fields is None:
        return review_result("missing_attachment")
    if not isinstance(si_fields, Mapping) or not isinstance(bl_fields, Mapping):
        raise TypeError("si_fields and bl_fields must be mappings or None")

    field_confidences = field_confidences or {}
    comparisons = []
    missing_fields = []

    for field in COMPARISON_FIELDS:
        si_value = si_fields.get(field)
        bl_value = bl_fields.get(field)
        si_normalized = normalize_value(field, si_value)
        bl_normalized = normalize_value(field, bl_value)

        if (
            is_missing(si_value)
            or is_missing(bl_value)
            or si_normalized is None
            or bl_normalized is None
        ):
            missing_fields.append(field)
            continue

        comparisons.append(
            {
                "field": field,
                "si_value": si_value,
                "bl_value": bl_value,
                "match": si_normalized == bl_normalized,
                "confidence": float(field_confidences.get(field, 1.0)),
            }
        )

    if missing_fields:
        result = review_result("missing_value", comparisons)
        result["missing_fields"] = missing_fields
        return result

    defect_fields = [
        comparison["field"]
        for comparison in comparisons
        if not comparison["match"]
    ]

    return {
        "status": "MISMATCH" if defect_fields else "OK",
        "review_reason": None,
        "has_defect": bool(defect_fields),
        "defect_fields": defect_fields,
        "comparisons": comparisons,
    }
