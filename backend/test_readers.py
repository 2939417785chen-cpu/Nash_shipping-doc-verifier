"""Checks the file readers WITHOUT using Gemini. Run: python backend/test_readers.py"""
from pathlib import Path

import llm
import readers

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "attachments").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
ATTACH = matches[0] / "attachments"

# 1. Plain files: the text comes back, as one page
result = readers.read_attachment(ATTACH / "email_004_SI.txt")
assert result["status"] == "ok" and len(result["pages"]) == 1 and not result["ocr"]

# 2. A text PDF: page by page
result = readers.read_attachment(ATTACH / "email_313_SI.pdf")
assert result["status"] == "ok" and len(result["pages"]) >= 1
assert "\n".join(result["pages"]).strip() == result["text"]

# 3. A picture-only PDF with ocr=False stays 'scanned' and nothing goes online
result = readers.read_attachment(ATTACH / "email_512_SI.pdf", ocr=False)
assert result["status"] == "scanned" and result["text"] == ""

# 4. A broken PDF is 'unreadable' (the AI is never asked)
assert readers.read_attachment(ATTACH / "email_511_BL.pdf")["status"] == "unreadable"

# 5. A picture-only PDF with ocr=True: the page is turned into a real PNG picture
#    and the (fake) AI answer becomes the text
sent = []
def fake_transcribe(png_bytes):
    sent.append(png_bytes)
    return "Shipper: FAKE OCR TEXT"
real_transcribe = llm.transcribe_image
llm.transcribe_image = fake_transcribe
result = readers.read_attachment(ATTACH / "email_512_SI.pdf")
assert result["status"] == "ok" and result["ocr"] is True
assert result["text"] == "Shipper: FAKE OCR TEXT" and result["pages"] == ["Shipper: FAKE OCR TEXT"]
assert len(sent) == 1 and sent[0][:8] == b"\x89PNG\r\n\x1a\n"

# 6. If the AI fails, the file stays 'scanned' with a reason (so a person can look at it)
def failing_transcribe(png_bytes):
    raise llm.LLMError("AI call failed: 503")
llm.transcribe_image = failing_transcribe
result = readers.read_attachment(ATTACH / "email_512_SI.pdf")
assert result["status"] == "scanned" and "503" in result["note"] and result["ocr"] is False
llm.transcribe_image = real_transcribe

print("All reader tests passed")