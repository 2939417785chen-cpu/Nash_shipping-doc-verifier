"""Tests for deterministic evidence-to-page location."""

import unittest

from backend.evidence import enrich_field_evidence, locate_evidence_page


class EvidenceTests(unittest.TestCase):
    def test_exact_evidence_is_located_on_correct_page(self):
        page, verified = locate_evidence_page(
            "Gross Weight: 13,500 KG",
            ["Shipper: Nash Paper", "GROSS WEIGHT 13,500 kg"],
        )
        self.assertEqual(page, 2)
        self.assertTrue(verified)

    def test_small_ocr_difference_uses_fuzzy_fallback(self):
        page, verified = locate_evidence_page(
            "Consignee: BLUE OCEAN TRADING LIMITED",
            ["CONSIGNEE BLUE 0CEAN TRADING LIMITED"],
        )
        self.assertEqual(page, 1)
        self.assertTrue(verified)

    def test_unverifiable_evidence_has_no_page(self):
        page, verified = locate_evidence_page("Invented Company Name", ["Other text"])
        self.assertIsNone(page)
        self.assertFalse(verified)

    def test_enrichment_does_not_mutate_cached_extraction(self):
        fields = {"shipper": {"value": "Nash", "evidence": "Shipper: Nash"}}
        enriched = enrich_field_evidence(
            fields,
            {"text": "Shipper: Nash", "pages": ["Title", "Shipper: Nash"]},
        )
        self.assertEqual(fields["shipper"]["evidence"], "Shipper: Nash")
        self.assertEqual(
            enriched["shipper"]["evidence"],
            {
                "snippet": "Shipper: Nash",
                "page": 2,
                "verified": True,
                "page_source": "snippet",
            },
        )

    def test_value_can_locate_page_when_ai_rephrases_label(self):
        fields = {
            "consignee": {
                "value": "UAB NOVAKOPA",
                "evidence": "Consignee: UAB NOVAKOPA",
            }
        }
        enriched = enrich_field_evidence(
            fields,
            {"text": "To the Order of: UAB NOVAKOPA"},
        )
        evidence = enriched["consignee"]["evidence"]
        self.assertEqual(evidence["page"], 1)
        self.assertEqual(evidence["page_source"], "value")
        self.assertFalse(evidence["verified"])


if __name__ == "__main__":
    unittest.main()
