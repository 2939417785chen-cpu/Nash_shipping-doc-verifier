"""Tests for the official OK, MISMATCH, and NEEDS_REVIEW policy."""

import unittest

from backend.decision import decide_status
from backend.result_validator import assert_valid_result


def comparison_result(
    *,
    defects=None,
    missing=None,
    uncertain=None,
):
    defects = defects or []
    missing = missing or []
    uncertain = uncertain or []
    comparisons = []
    for field in ("shipper", "consignee", "notify_party"):
        if field in missing:
            match = None
        elif field in defects:
            match = False
        else:
            match = True
        comparisons.append(
            {
                "field": field,
                "si_value": "SI value",
                "bl_value": "BL value",
                "match": match,
                "confidence": 0.6 if field in uncertain else 0.95,
            }
        )
    return {
        "comparisons": comparisons,
        "defect_fields": defects,
        "missing_fields": missing,
        "uncertain_fields": uncertain,
    }


def validate_bl(decision):
    return assert_valid_result({"category": "BL_COMPARISON", **decision})


class DecisionTests(unittest.TestCase):
    def test_complete_match_is_ok(self):
        decision = decide_status(comparison_result())

        self.assertEqual(decision["status"], "OK")
        validate_bl(decision)

    def test_clear_difference_is_mismatch(self):
        decision = decide_status(comparison_result(defects=["consignee"]))

        self.assertEqual(decision["status"], "MISMATCH")
        self.assertEqual(decision["defect_fields"], ["consignee"])
        validate_bl(decision)

    def test_missing_value_requires_review(self):
        decision = decide_status(comparison_result(missing=["notify_party"]))

        self.assertEqual(decision["status"], "NEEDS_REVIEW")
        self.assertEqual(decision["review_reason"], "missing_value")
        validate_bl(decision)

    def test_uncertain_difference_requires_review(self):
        decision = decide_status(
            comparison_result(
                defects=["consignee"],
                uncertain=["consignee"],
            )
        )

        self.assertEqual(decision["status"], "NEEDS_REVIEW")
        self.assertEqual(decision["review_reason"], "unreadable")
        validate_bl(decision)

    def test_clear_defect_takes_precedence_over_other_uncertainty(self):
        decision = decide_status(
            comparison_result(
                defects=["shipper", "consignee"],
                uncertain=["consignee"],
            )
        )

        self.assertEqual(decision["status"], "MISMATCH")
        self.assertEqual(decision["defect_fields"], ["shipper"])
        self.assertEqual(decision["uncertain_fields"], ["consignee"])
        validate_bl(decision)

    def test_missing_attachment_requires_review(self):
        decision = decide_status(missing_attachment=True)

        self.assertEqual(decision["review_reason"], "missing_attachment")
        validate_bl(decision)

    def test_unreadable_reader_result_requires_review(self):
        decision = decide_status(reader_results={"SI": {"status": "unreadable"}})

        self.assertEqual(decision["review_reason"], "unreadable")
        validate_bl(decision)


if __name__ == "__main__":
    unittest.main()
