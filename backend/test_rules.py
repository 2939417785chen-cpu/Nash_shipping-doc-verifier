"""Checks rules.py on the real data. Run: python backend/test_rules.py   (no AI, no internet)"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules
from readers import read_attachment

REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
BUNDLE = matches[0]
emails = [json.loads(p.read_text()) for p in sorted((BUNDLE / "inbox").glob("email_*.json"))]

# 1. draft BL requests: only emails WITHOUT attachments, and not the SI requests that mention a draft BL
requests = [e["email_id"] for e in emails if rules.is_draft_bl_request(e)]
assert all(not e["attachments"] for e in emails if e["email_id"] in requests)
assert not rules.is_draft_bl_request({"attachments": ["a.txt"], "body": "Please send the draft BL for X"})
assert rules.is_draft_bl_request({"attachments": [], "body": "Please assist to send the draft BL for X for checking asap."})
assert not rules.is_draft_bl_request({"attachments": [], "body": "Please compare the SI and draft BL for X and confirm."})
print(f"draft BL requests found: {len(requests)}")
assert len(requests) == 91

# 2. wrong document type, on every SI / BL attachment
wrong, kinds = [], Counter()
for e in emails:
    for path in e["attachments"]:
        role = "SI" if "_SI" in path else "BL"
        text = read_attachment(BUNDLE / path, ocr=False)["text"]
        kinds[(role, rules.document_kind(text))] += 1
        if rules.is_wrong_document(role, text):
            wrong.append((e["email_id"], role, rules.document_kind(text)))
print("document kinds seen (role, kind):", dict(kinds))
print("wrong documents found:", wrong)
assert len(wrong) == 5 and all(w[1] == "BL" for w in wrong)

# 3. blank required values
blank = []
for e in emails:
    for path in e["attachments"]:
        role = "SI" if "_SI" in path else "BL"
        text = read_attachment(BUNDLE / path, ocr=False)["text"]
        fields = rules.blank_required_fields(text)
        if fields:
            blank.append((e["email_id"], role, fields))
print("blank required values found:", len(blank))
for item in blank[:12]:
    print("   ", item)
assert len(blank) == 5 and all(b[1] == "SI" for b in blank)
print("All rule checks passed")