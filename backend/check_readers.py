from pathlib import Path
from collections import Counter
from readers import read_attachment

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "attachments").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
ATTACH_DIR = matches[0] / "attachments"

counts = Counter()
problems = []
for path in sorted(ATTACH_DIR.iterdir()):
    result = read_attachment(path, ocr=False)
    counts[(path.suffix, result["status"])] += 1
    if result["status"] != "ok":
        problems.append((path.name, result["status"], result["note"]))

print("file type / status counts:")
for (suffix, status), n in sorted(counts.items()):
    print(f"  {suffix:6} {status:11} {n}")

print()
print("files that are not ok:")
for name, status, note in problems:
    print(f"  {name}: {status} ({note})")
