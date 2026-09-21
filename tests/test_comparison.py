"""Tests for the integrated normalizer and compare.py field engine."""

from decimal import Decimal
import unittest

from backend.compare import FIELDS, compare_fields
from backend.normalizer import (
    normalize_container_count,
    normalize_text,
    normalize_weight_kg,
)


BASE_VALUES = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "EAST BRIGHT FZ-LLC",
    "notify_party": "EAST BRIGHT FZ-LLC",
    "port_of_loading": "NANTONG, CHINA",
    "port_of_discharge": "KARACHI, PAKISTAN",
    "container_count": 6,
    "gross_weight_kg": 131058,
}


def extracted_fields(**overrides):
    values = {**BASE_VALUES, **overrides}
    return {
        field: {"value": value, "evidence": f"{field}: {value}"}
        for field, value in values.items()
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
        si_fields = extracted_fields()
        bl_fields = extracted_fields(
            consignee="east bright fz llc",
            port_of_loading="Nantong China",
            container_count="6 containers",
            gross_weight_kg="131.058 MT",
        )

        result = compare_fields(si_fields, bl_fields)

        self.assertEqual(result["defect_fields"], [])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(len(result["comparisons"]), len(FIELDS))

    def test_difference_creates_defect_field(self):
        result = compare_fields(
            extracted_fields(),
            extracted_fields(consignee="UAB NOVAKOPA"),
        )

        self.assertEqual(result["defect_fields"], ["consignee"])
        self.assertEqual(result["uncertain_fields"], [])

    def test_missing_value_is_reported_separately(self):
        result = compare_fields(
            extracted_fields(),
            extracted_fields(notify_party=None),
        )

        self.assertEqual(result["missing_fields"], ["notify_party"])
        self.assertEqual(result["defect_fields"], [])

    def test_similar_difference_is_uncertain(self):
        result = compare_fields(
            extracted_fields(),
            extracted_fields(consignee="EAST BRIGHT FZ-LIC"),
        )

        self.assertEqual(result["defect_fields"], ["consignee"])
        self.assertEqual(result["uncertain_fields"], ["consignee"])

    def test_evidence_is_preserved_for_review_ui(self):
        result = compare_fields(extracted_fields(), extracted_fields())

        consignee = next(
            item for item in result["comparisons"] if item["field"] == "consignee"
        )
        self.assertIn("consignee:", consignee["si_evidence"]["snippet"])


if __name__ == "__main__":
    unittest.main()
