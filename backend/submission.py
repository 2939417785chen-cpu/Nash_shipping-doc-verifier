"""Build an exact competition submission from richer pipeline results."""

import json
from pathlib import Path

from backend.result_validator import ResultValidationError, assert_valid_result


OFFICIAL_FIELDS = (
    "category",
    "status",
    "review_reason",
    "defect_fields",
    "has_defect",
)


class SubmissionValidationError(ValueError):
    """Raised when a submission is missing or contains unexpected emails."""


def load_expected_email_ids(sample_submission_path):
    """Read the required email IDs in official sample-submission order."""
    path = Path(sample_submission_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SubmissionValidationError("sample submission must be an object")
    return list(payload)


def build_submission(results, expected_email_ids=None):
    """Validate all results and keep only the five official output fields."""
    if not isinstance(results, dict):
        raise SubmissionValidationError("results must be keyed by email_id")

    if expected_email_ids is None:
        email_ids = list(results)
    else:
        email_ids = list(expected_email_ids)
        expected = set(email_ids)
        actual = set(results)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        problems = []
        if missing:
            problems.append("missing email IDs: " + ", ".join(missing))
        if unexpected:
            problems.append("unexpected email IDs: " + ", ".join(unexpected))
        if problems:
            raise SubmissionValidationError("; ".join(problems))

    submission = {}
    result_errors = []
    for email_id in email_ids:
        result = results[email_id]
        try:
            assert_valid_result(result)
        except ResultValidationError as error:
            result_errors.append(f'{email_id}: {"; ".join(error.errors)}')
            continue

        submission[email_id] = {
            field: result[field]
            for field in OFFICIAL_FIELDS
        }

    if result_errors:
        raise SubmissionValidationError(" | ".join(result_errors))
    return submission


def write_submission(results, output_path, expected_email_ids=None):
    """Build and write a UTF-8 JSON submission, returning its path."""
    submission = build_submission(results, expected_email_ids)
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(submission, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
