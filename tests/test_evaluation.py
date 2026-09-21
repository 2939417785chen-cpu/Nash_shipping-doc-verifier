"""Tests for label-free quality reporting and official score submission."""

import unittest

from backend.evaluation import build_quality_report, submit_for_official_score


def result(**overrides):
    base = {
        "category": "BL_COMPARISON",
        "status": "OK",
        "review_reason": None,
        "has_defect": False,
        "defect_fields": [],
        "classification_confidence": 0.9,
        "comparisons": [],
    }
    base.update(overrides)
    return base


class EvaluationTests(unittest.TestCase):
    def test_report_counts_review_and_evidence_quality(self):
        comparison = {
            "field": "shipper",
            "match": True,
            "si_evidence": {"snippet": "A", "page": 1, "verified": True},
            "bl_evidence": {"snippet": "B", "page": None, "verified": False},
        }
        results = {
            "email_001": result(
                classification_confidence=0.6,
                comparisons=[comparison],
            ),
            "email_002": result(
                status="NEEDS_REVIEW",
                review_reason="missing_attachment",
            ),
        }
        report = build_quality_report(results, {"email_003": "failure"})
        self.assertEqual(report["processed"], 2)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["review_reasons"], {"missing_attachment": 1})
        self.assertEqual(report["low_confidence_ids"], ["email_001"])
        self.assertEqual(report["evidence"]["coverage"], 1.0)
        self.assertEqual(report["evidence"]["verification_rate"], 0.5)

    def test_official_submit_receives_only_official_fields(self):
        received = {}

        def fake_submit(submission):
            received.update(submission)
            return {"final_score": 0.8}

        response = submit_for_official_score(
            {"email_001": result()}, ["email_001"], fake_submit
        )
        self.assertEqual(response, {"final_score": 0.8})
        self.assertNotIn("comparisons", received["email_001"])
        self.assertNotIn("classification_confidence", received["email_001"])


if __name__ == "__main__":
    unittest.main()
