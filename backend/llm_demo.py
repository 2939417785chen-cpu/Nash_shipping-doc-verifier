"""Try the AI on a few real emails. Run: python3 backend/llm_demo.py"""
print("Loading libraries, this can take up to a minute...", flush=True)

from pathlib import Path

import llm
from loader import Inbox
from readers import read_attachment

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
DATA_DIR = matches[0]
inbox = Inbox(str(DATA_DIR))

# A mix of emails that look different from each other
SAMPLES = ["email_002", "email_007", "email_012", "email_072", "email_004"]


def show_classification():
    print("== classify ==")
    for email_id in SAMPLES:
        email = inbox.get(email_id)
        try:
            result = llm.classify_email(email)
        except llm.LLMError as e:
            print(f"{email_id}  FAILED: {e}")
            continue
        print(f"{email_id}  {result['category']:14} {result['confidence']:.2f}  {email['subject'][:50]}")
        print(f"           why: {result['reason']}")


def show_extraction(email_id):
    print(f"\n== extract fields from {email_id} ==")
    email = inbox.get(email_id)
    docs = {}
    for path in email["attachments"]:
        kind = "SI" if "_SI" in path else "BL"
        content = read_attachment(DATA_DIR / path)
        if content["status"] != "ok":
            print(f"{kind}: cannot read ({content['status']})")
            continue
        try:
            docs[kind] = llm.extract_fields(content["text"], kind)
        except llm.LLMError as e:
            print(f"{kind}: AI failed: {e}")
    if len(docs) < 2:
        return
    print(f"{'field':19}{'SI':34}{'BL':34}")
    for field in llm.FIELDS:
        si, bl = docs["SI"][field]["value"], docs["BL"][field]["value"]
        print(f"{field:19}{str(si):34}{str(bl):34}")


if __name__ == "__main__":
    show_classification()
    show_extraction("email_004")