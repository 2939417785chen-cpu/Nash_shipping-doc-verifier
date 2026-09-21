"""Tests for end-to-end orchestration without making Gemini API calls."""

import unittest
from backend.pipeline import (
    identify_document_attachments,
    process_email,
    run_pipeline,
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


class FakeLLMError(Exception):
    pass


def email_record(*attachments):
    return {
        "email_id": "email_004",
        "from": "shipping@example.com",
        "subject": "Please verify the draft BL",
        "body": "Please compare the attached documents.",
        "attachments": list(attachments),
    }


def classify(category="BL_COMPARISON"):
    def fake(_email):
        return {"category": category, "confidence": 0.98, "reason": "test"}

    return fake


def read_ok(_path, ocr=True):
    return {
        "text": "document text",
        "pages": ["document text"],
        "status": "ok",
        "note": "",
        "ocr": False,
    }


def extract_with_bl_mismatch(_text, doc_type):
    values = dict(BASE_VALUES)
    if doc_type == "BL":
        values["consignee"] = "UAB NOVAKOPA"
    return {
        field: {"value": value, "evidence": f"{field}: {value}"}
        for field, value in values.items()
    }


class AttachmentTests(unittest.TestCase):
    def test_official_filenames_are_identified(self):
        documents = identify_document_attachments(
            ["attachments/email_004_SI.txt", "attachments/email_004_BL.txt"]
        )

        self.assertFalse(documents["missing_attachment"])
        self.assertFalse(documents["wrong_doc_type"])


class ProcessEmailTests(unittest.TestCase):
    def test_non_bl_email_stops_after_classification(self):
        result = process_email(
            email_record(),
            "data",
            classify_fn=classify("GENERAL"),
        )

        self.assertEqual(result["category"], "GENERAL")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["comparisons"], [])

    def test_bl_email_runs_read_extract_compare_and_decision(self):
        result = process_email(
            email_record(
                "attachments/email_004_SI.txt",
                "attachments/email_004_BL.txt",
            ),
            "data",
            classify_fn=classify(),
            read_fn=read_ok,
            extract_fn=extract_with_bl_mismatch,
        )

        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["defect_fields"], ["consignee"])
        self.assertEqual(len(result["comparisons"]), 7)

    def test_pipeline_adds_document_page_to_evidence(self):
        def read_with_pages(path, ocr=True):
            doc_type = "SI" if "_SI." in str(path) else "BL"
            values = dict(BASE_VALUES)
            if doc_type == "BL":
                values["consignee"] = "UAB NOVAKOPA"
            evidence_lines = [f"{field}: {value}" for field, value in values.items()]
            return {
                "text": "\n".join(evidence_lines),
                "pages": ["cover", "\n".join(evidence_lines)],
                "status": "ok",
                "note": "",
                "ocr": False,
            }

        result = process_email(
            email_record(
                "attachments/email_004_SI.txt",
                "attachments/email_004_BL.txt",
            ),
            "data",
            classify_fn=classify(),
            read_fn=read_with_pages,
            extract_fn=extract_with_bl_mismatch,
        )

        consignee = next(
            item for item in result["comparisons"] if item["field"] == "consignee"
        )
        self.assertEqual(consignee["si_evidence"]["page"], 2)
        self.assertTrue(consignee["si_evidence"]["verified"])
        self.assertEqual(consignee["bl_evidence"]["page"], 2)

    def test_missing_bl_attachment_requires_review(self):
        result = process_email(
            email_record("attachments/email_004_SI.txt"),
            "data",
            classify_fn=classify(),
        )

        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["review_reason"], "missing_attachment")

    def test_unreadable_attachment_requires_review(self):
        def unreadable(_path, ocr=True):
            return {"text": "", "status": "unreadable", "note": "broken"}

        result = process_email(
            email_record(
                "attachments/email_004_SI.pdf",
                "attachments/email_004_BL.pdf",
            ),
            "data",
            classify_fn=classify(),
            read_fn=unreadable,
        )

        self.assertEqual(result["review_reason"], "unreadable")

    def test_extraction_failure_becomes_human_review(self):
        def failing_extract(_text, _doc_type):
            raise FakeLLMError("temporary API failure")

        result = process_email(
            email_record(
                "attachments/email_004_SI.txt",
                "attachments/email_004_BL.txt",
            ),
            "data",
            classify_fn=classify(),
            read_fn=read_ok,
            extract_fn=failing_extract,
            llm_error_type=FakeLLMError,
        )

        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["review_reason"], "unreadable")


class BatchTests(unittest.TestCase):
    def test_one_failure_does_not_stop_later_emails(self):
        emails = [
            {"email_id": "email_bad"},
            {"email_id": "email_good"},
        ]

        def fake_process(email, _source):
            if email["email_id"] == "email_bad":
                raise FakeLLMError("failed")
            return {"email_id": email["email_id"]}

        results, errors = run_pipeline(
            "data",
            emails=emails,
            process_fn=fake_process,
        )

        self.assertIn("email_good", results)
        self.assertIn("email_bad", errors)


if __name__ == "__main__":
    unittest.main()
