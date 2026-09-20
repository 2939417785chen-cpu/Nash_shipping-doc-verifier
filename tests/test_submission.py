"""Tests for result validation and exact competition submission output."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.result_validator import assert_valid_result, validate_result
from backend.submission import (
    OFFICIAL_FIELDS,
    SubmissionValidationError,
    build_submission,
    load_expected_email_ids,
    write_submission,
)


GENERAL_RESULT = {
    "category": "GENERAL",
    "status": "OK",
    "review_reason": None,
    "defect_fields": [],
    "has_defect": False,
}

MISMATCH_RESULT = {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": None,
    "defect_fields": ["consignee"],
    "has_defect": True,
    "comparisons": [
        {
            "field": "consignee",
            "si_value": "EAST BRIGHT FZ-LLC",
            "bl_value": "UAB NOVAKOPA",
            "match": False,
            "confidence": 0.99,
        }
    ],
    "classification_confidence": 0.98,
}


class ResultValidatorTests(unittest.TestCase):
    def test_valid_general_result(self):
        self.assertEqual(validate_result(GENERAL_RESULT), [])

    def test_ok_result_cannot_claim_a_defect(self):
        result = {
            **GENERAL_RESULT,
            "category": "BL_COMPARISON",
            "has_defect": True,
            "defect_fields": ["consignee"],
        }

        errors = validate_result(result)

        self.assertIn("OK result must set has_defect to false", errors)
        self.assertIn("OK result must have empty defect_fields", errors)

    def test_mismatch_requires_defect_fields(self):
        result = {
            **MISMATCH_RESULT,
            "defect_fields": [],
            "comparisons": [],
        }

        errors = validate_result(result)

        self.assertIn(
            "MISMATCH result must list at least one defect field",
            errors,
        )

    def test_invalid_review_reason_is_rejected(self):
        result = {
            **GENERAL_RESULT,
            "category": "BL_COMPARISON",
            "status": "NEEDS_REVIEW",
            "review_reason": "model_was_unsure",
        }

        errors = validate_result(result)

        self.assertIn("unsupported review_reason: model_was_unsure", errors)

    def test_comparisons_must_match_defect_fields(self):
        result = {
            **MISMATCH_RESULT,
            "defect_fields": ["shipper"],
        }

        errors = validate_result(result)

        self.assertIn("comparison mismatches must equal defect_fields", errors)

    def test_assert_valid_result_returns_valid_input(self):
        self.assertIs(assert_valid_result(MISMATCH_RESULT), MISMATCH_RESULT)


class SubmissionTests(unittest.TestCase):
    def test_build_submission_removes_ui_only_fields(self):
        submission = build_submission({"email_004": MISMATCH_RESULT})

        self.assertEqual(
            tuple(submission["email_004"]),
            OFFICIAL_FIELDS,
        )
        self.assertNotIn("comparisons", submission["email_004"])
        self.assertNotIn("classification_confidence", submission["email_004"])

    def test_expected_email_ids_must_match_exactly(self):
        with self.assertRaisesRegex(
            SubmissionValidationError,
            "missing email IDs: email_002",
        ):
            build_submission(
                {"email_001": GENERAL_RESULT},
                expected_email_ids=["email_001", "email_002"],
            )

    def test_invalid_email_result_identifies_email_id(self):
        invalid = {**GENERAL_RESULT, "category": "UNKNOWN"}

        with self.assertRaisesRegex(
            SubmissionValidationError,
            "email_001: unsupported category",
        ):
            build_submission({"email_001": invalid})

    def test_write_submission_produces_valid_json(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "submission.json"
            write_submission({"email_001": GENERAL_RESULT}, output)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload, {"email_001": GENERAL_RESULT})

    def test_load_expected_email_ids_preserves_sample_order(self):
        with TemporaryDirectory() as directory:
            sample_path = Path(directory) / "sample_submission.json"
            sample_path.write_text(
                json.dumps(
                    {
                        "email_002": GENERAL_RESULT,
                        "email_001": GENERAL_RESULT,
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_expected_email_ids(sample_path),
                ["email_002", "email_001"],
            )


if __name__ == "__main__":
    unittest.main()
