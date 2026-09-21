"""Read the picture-only PDFs with AI vision (uses Gemini). Run: python backend/ocr_demo.py"""
print("Loading libraries...", flush=True)
from pathlib import Path

from readers import read_attachment

# The data bundle folder sits next to this repo folder
REPO_ROOT = Path(__file__).resolve().parent.parent
matches = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
if not matches or not (matches[0] / "attachments").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
ATTACH = matches[0] / "attachments"

for name in ["email_512_SI.pdf", "email_512_BL.pdf"]:
    result = read_attachment(ATTACH / name)
    print(f"== {name}: {result['status']}, {len(result['pages'])} page(s), {result['note']}")
    print(result["text"] or "(no text)")
    print()