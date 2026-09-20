"""Validate pipeline results before they reach the UI or competition output."""

from collections.abc import Mapping

from backend.comparison import COMPARISON_FIELDS, REVIEW_REASONS


CATEGORIES = {
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
}

STATUSES = {"OK", "MISMATCH", "NEEDS_REVIEW"}

REQUIRED_RESULT_FIELDS = {
    "category",
    "status",
    "review_reason",
    "defect_fields",
    "has_defect",
}


class ResultValidationError(ValueError):
    """Raised when a pipeline result contradicts the competition rules."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _validate_defect_fields(defect_fields, errors):
    if not isinstance(defect_fields, list):
        errors.append("defect_fields must be a list")
        return

    invalid_fields = [
        field for field in defect_fields if field not in COMPARISON_FIELDS
    ]
    if invalid_fields:
        errors.append(
            "defect_fields contains unsupported fields: "
            + ", ".join(map(str, invalid_fields))
        )
    if len(defect_fields) != len(set(defect_fields)):
        errors.append("defect_fields must not contain duplicates")


def _validate_comparisons(result, errors):
    """Cross-check optional UI comparisons with the official result fields."""
    if "comparisons" not in result:
        return

    comparisons = result["comparisons"]
    if not isinstance(comparisons, list):
        errors.append("comparisons must be a list when provided")
        return

    seen_fields = set()
    mismatched_fields = []
    for index, comparison in enumerate(comparisons):
        if not isinstance(comparison, Mapping):
            errors.append(f"comparisons[{index}] must be an object")
            continue

        field = comparison.get("field")
        match = comparison.get("match")
        if field not in COMPARISON_FIELDS:
            errors.append(f"comparisons[{index}] has unsupported field: {field}")
        elif field in seen_fields:
            errors.append(f"comparisons contains duplicate field: {field}")
        else:
            seen_fields.add(field)

        if not isinstance(match, bool):
            errors.append(f"comparisons[{index}].match must be a boolean")
        elif not match and field in COMPARISON_FIELDS:
            mismatched_fields.append(field)

    status = result.get("status")
    if status == "OK" and mismatched_fields:
        errors.append("OK result cannot contain mismatched comparisons")
    if status == "MISMATCH" and set(mismatched_fields) != set(
        result.get("defect_fields", [])
    ):
        errors.append("comparison mismatches must equal defect_fields")


def validate_result(result):
    """Return a list of human-readable validation errors for one email result."""
    if not isinstance(result, Mapping):
        return ["result must be an object"]

    errors = []
    missing_keys = sorted(REQUIRED_RESULT_FIELDS - set(result))
    if missing_keys:
        errors.append("missing required fields: " + ", ".join(missing_keys))
        return errors

    category = result["category"]
    status = result["status"]
    review_reason = result["review_reason"]
    defect_fields = result["defect_fields"]
    has_defect = result["has_defect"]

    if category not in CATEGORIES:
        errors.append(f"unsupported category: {category}")
    if status not in STATUSES:
        errors.append(f"unsupported status: {status}")
    if not isinstance(has_defect, bool):
        errors.append("has_defect must be a boolean")

    _validate_defect_fields(defect_fields, errors)

    if category != "BL_COMPARISON":
        if status != "OK":
            errors.append("non-BL categories must use status OK")
        if review_reason is not None:
            errors.append("non-BL categories must not have a review_reason")
        if has_defect is not False:
            errors.append("non-BL categories must not have a document defect")
        if defect_fields != []:
            errors.append("non-BL categories must have empty defect_fields")
    elif status == "OK":
        if review_reason is not None:
            errors.append("OK result must not have a review_reason")
        if has_defect is not False:
            errors.append("OK result must set has_defect to false")
        if defect_fields != []:
            errors.append("OK result must have empty defect_fields")
    elif status == "MISMATCH":
        if review_reason is not None:
            errors.append("MISMATCH result must not have a review_reason")
        if has_defect is not True:
            errors.append("MISMATCH result must set has_defect to true")
        if not defect_fields:
            errors.append("MISMATCH result must list at least one defect field")
    elif status == "NEEDS_REVIEW":
        if review_reason not in REVIEW_REASONS:
            errors.append(f"unsupported review_reason: {review_reason}")
        if has_defect is not False:
            errors.append("NEEDS_REVIEW result must set has_defect to false")
        if defect_fields != []:
            errors.append("NEEDS_REVIEW result must have empty defect_fields")

    _validate_comparisons(result, errors)
    return errors


def assert_valid_result(result):
    """Raise ResultValidationError when a result is invalid."""
    errors = validate_result(result)
    if errors:
        raise ResultValidationError(errors)
    return result
