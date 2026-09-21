"""Run the pipeline on a hand-picked sample of emails and print one line per email.

Run it from the repo folder (not from inside backend):
    python -m backend.run_sample
"""
import time
from pathlib import Path

from backend import pipeline
from backend.loader import Inbox

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
SOURCE = matches[0]

# A mix on purpose: text pairs, xlsx, xlsx + docx, text PDF, scanned PDF,
# broken PDFs, emails with only one attachment, and emails without attachments
SAMPLE_IDS = [
    "email_001", "email_004", "email_009", "email_013", "email_025", "email_031",  # txt + txt
    "email_005",                # xlsx + xlsx
    "email_055",                # xlsx + docx
    "email_313",                # text PDF
    "email_512",                # scanned PDF (read by AI vision)
    "email_511", "email_515",   # broken BL PDF
    "email_507", "email_509",   # only one attachment
    "email_002", "email_003", "email_006", "email_007", "email_012", "email_072",  # no attachments
]


def main():
    inbox = {e["email_id"]: e for e in Inbox(str(SOURCE)).emails()}
    emails = [inbox[i] for i in SAMPLE_IDS if i in inbox]
    print(f"Running {len(emails)} emails (about 40 AI calls, roughly 4 to 6 minutes)...", flush=True)

    started = time.time()
    results, errors = pipeline.run_pipeline(SOURCE, emails=emails)
    print(f"Done in {time.time() - started:.0f} seconds. Results: {len(results)}, errors: {len(errors)}\n")

    print(f"{'email':11}{'category':15}{'status':14}{'review_reason':19}defect_fields")
    for email_id in SAMPLE_IDS:
        if email_id in results:
            r = results[email_id]
            print(f"{email_id:11}{str(r.get('category')):15}{str(r.get('status')):14}"
                  f"{str(r.get('review_reason')):19}{r.get('defect_fields')}")
            if r.get("status") == "NEEDS_REVIEW":
                for warning in r.get("warnings", []):
                    print(f"{'':11}note: {warning}")
        elif email_id in errors:
            print(f"{email_id:11}ERROR: {errors[email_id]}")


if __name__ == "__main__":
    main()