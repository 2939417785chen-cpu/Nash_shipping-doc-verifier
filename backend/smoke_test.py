from pathlib import Path
from collections import Counter
from loader import Inbox

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
DATA_DIR = matches[0]

inbox = Inbox(str(DATA_DIR))
emails = inbox.emails()

print("data folder:", DATA_DIR.name)
print("emails:", len(emails))
print("attachments per email:", Counter(len(e["attachments"]) for e in emails))
print("file types:", Counter(Path(a).suffix for e in emails for a in e["attachments"]))
