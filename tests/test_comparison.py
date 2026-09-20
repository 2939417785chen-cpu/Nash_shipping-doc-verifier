"""Tests for field normalization and SI/BL comparison decisions."""

from decimal import Decimal
import unittest

from backend.comparison import COMPARISON_FIELDS, compare_documents, review_result
from backend.normalizer import (
    normalize_container_count,
    normalize_text,
    normalize_weight_kg,
)


BASE_DOCUMENT = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "EAST BRIGHT FZ-LLC",
    "notify_party": "EAST BRIGHT FZ-LLC",
    "port_of_loading": "NANTONG, CHINA",
    "port_of_discharge": "KARACHI, PAKISTAN",
    "container_count": 6,
    "gross_weight_kg": 131058,
}


class NormalizerTests(unittest.TestCase):
    def test_text_ignores_case_spacing_and_punctuation(self):
        self.assertEqual(
            normalize_text(" East Bright FZ-LLC "),
            normalize_text("EAST   BRIGHT FZ LLC"),
        )

    def test_container_count_accepts_common_labels(self):
        self.assertEqual(normalize_container_count("6 x 40HQ containers"), 6)

    def test_metric_tonnes_are_converted_to_kg(self):
        self.assertEqual(normalize_weight_kg("131.058 MT"), Decimal("131058"))


class ComparisonTests(unittest.TestCase):
    def test_all_fields_match_after_normalization(self):
        draft_bl = dict(BASE_DOCUMENT)
        draft_bl["consignee"] = "east bright fz llc"
        draft_bl["port_of_loading"] = "Nantong China"
        draft_bl["container_count"] = "6 containers"
        draft_bl["gross_weight_kg"] = "131.058 MT"

        result = compare_documents(BASE_DOCUMENT, draft_bl)

        self.assertEqual(result["status"], "OK")
        self.assertFalse(result["has_defect"])
        self.assertEqual(result["defect_fields"], [])
        self.assertEqual(len(result["comparisons"]), len(COMPARISON_FIELDS))

    def test_difference_creates_mismatch_and_defect_field(self):
        draft_bl = dict(BASE_DOCUMENT)
        draft_bl["consignee"] = "UAB NOVAKOPA"

        result = compare_documents(BASE_DOCUMENT, draft_bl)

        self.assertEqual(result["status"], "MISMATCH")
        self.assertTrue(result["has_defect"])
        self.assertEqual(result["defect_fields"], ["consignee"])

    def test_missing_value_requires_review(self):
        draft_bl = dict(BASE_DOCUMENT)
        draft_bl["notify_party"] = ""

        result = compare_documents(BASE_DOCUMENT, draft_bl)

        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["review_reason"], "missing_value")
        self.assertEqual(result["missing_fields"], ["notify_party"])
        self.assertFalse(result["has_defect"])

    def test_missing_document_requires_review(self):
        result = compare_documents(BASE_DOCUMENT, None)

        self.assertEqual(result, review_result("missing_attachment"))

    def test_explicit_unreadable_review_result(self):
        result = review_result("unreadable")

        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["review_reason"], "unreadable")


if __name__ == "__main__":
    unittest.main()
