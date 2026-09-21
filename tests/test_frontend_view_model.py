"""Tests for frontend formatting across demo and live result schemas."""

import unittest

from frontend.view_model import (
    comparison_label,
    display_value,
    evidence_caption,
    evidence_snippet,
    human_attention_label,
    ocr_documents,
)


class FrontendViewModelTests(unittest.TestCase):
    def test_comparison_label_distinguishes_missing_from_mismatch(self):
        self.assertEqual(comparison_label(True), "✅ Match")
        self.assertEqual(comparison_label(False), "❌ Mismatch")
        self.assertEqual(comparison_label(None), "⚠️ Needs review")

    def test_evidence_supports_live_backend_schema(self):
        evidence = {
            "snippet": "Consignee: Nash Ltd",
            "page": 2,
            "verified": True,
            "page_source": "snippet",
        }
        self.assertEqual(evidence_snippet(evidence), "Consignee: Nash Ltd")
        self.assertEqual(
            evidence_caption(evidence, "Shipping Instruction"),
            "Shipping Instruction · page 2 · snippet verified",
        )

    def test_evidence_supports_old_demo_schema(self):
        evidence = {"text": "Notify: Nash Ltd", "source": "sample.pdf", "page": 1}
        self.assertEqual(evidence_snippet(evidence), "Notify: Nash Ltd")
        self.assertEqual(evidence_caption(evidence), "sample.pdf · page 1")

    def test_value_fallback_is_explained(self):
        evidence = {
            "snippet": "Consignee: Nash",
            "page": 3,
            "verified": False,
            "page_source": "value",
        }
        self.assertIn("page located from extracted value", evidence_caption(evidence))

    def test_display_value_preserves_zero(self):
        self.assertEqual(display_value(0), 0)
        self.assertEqual(display_value(None), "—")

    def test_successful_ocr_recommends_human_attention(self):
        result = {
            "status": "OK",
            "document_reading": {
                "SI": {"status": "ok", "ocr": True},
                "BL": {"status": "ok", "ocr": False},
            },
        }
        self.assertEqual(ocr_documents(result), ["SI"])
        self.assertEqual(human_attention_label(result), "Recommended")

    def test_non_ok_status_still_requires_attention(self):
        self.assertEqual(human_attention_label({"status": "MISMATCH"}), "Required")


if __name__ == "__main__":
    unittest.main()
