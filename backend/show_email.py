"""Show the field-by-field result of one email (uses the saved AI answers, so it is free).

Run it from the repo folder:
    python -m backend.show_email email_055
"""
import sys
from pathlib import Path

from backend import pipeline
from backend.loader import Inbox

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
SOURCE = matches[0]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m backend.show_email email_055")
    email_id = sys.argv[1]
    emails = {e["email_id"]: e for e in Inbox(str(SOURCE)).emails()}
    if email_id not in emails:
        raise SystemExit(f"No such email: {email_id}")

    email = emails[email_id]
    print(f"{email_id} | subject: {email['subject'][:70]}")
    result = pipeline.process_email(email, SOURCE)
    print(f"category={result.get('category')}  status={result.get('status')}  "
          f"review_reason={result.get('review_reason')}  defect_fields={result.get('defect_fields')}\n")
    for item in result.get("comparisons", []):
        print(f"{item['field']:18} match={str(item['match']):6} confidence={item.get('confidence')}")
        print(f"    SI: {item['si_value']!r}")
        print(f"    BL: {item['bl_value']!r}")


if __name__ == "__main__":
    main()