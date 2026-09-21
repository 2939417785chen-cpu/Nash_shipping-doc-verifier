"""See where points are lost: compare our saved results with the organizers' answer file.

The organizers said the answer file is there for us to check our own work.
Use it to find KINDS of mistakes, never to copy answers for single emails.

Run it from the repo folder, after backend.run_full has finished:
    python -m backend.diagnose
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from backend.loader import Inbox

REPO_ROOT = Path(__file__).resolve().parent.parent
bundles = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
dockers = sorted(REPO_ROOT.parent.glob("sdoc-hac*docker"))
if not bundles or not dockers:
    raise SystemExit("Could not find the bundle and docker folders next to the repo")
TRUTH_FILE = dockers[0] / "data_v2" / "ground_truth.json"
RESULTS_FILE = REPO_ROOT / "backend" / ".cache" / "results.json"


def first_sentence(body):
    """The first real sentence of the email body (after the greeting)."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    text = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
    return re.sub(r"\s+", " ", text)[:90]


def main():
    truth = json.loads(TRUTH_FILE.read_text())
    results = json.loads(RESULTS_FILE.read_text())
    emails = {e["email_id"]: e for e in Inbox(str(bundles[0])).emails()}

    # A. classification mistakes
    print("A. CLASSIFICATION MISTAKES (true -> what we said)")
    groups = defaultdict(list)
    for eid, t in truth.items():
        got = results[eid]["category"]
        if got != t["category"]:
            groups[(t["category"], got)].append(eid)
    if not groups:
        print("   none")
    for (true, got), ids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        with_att = sum(1 for i in ids if emails[i]["attachments"])
        print(f"\n   {true} -> {got}: {len(ids)} emails ({with_att} with attachments)")
        for sentence, n in Counter(first_sentence(emails[i]["body"]) for i in ids).most_common(4):
            print(f"      {n:3} x {sentence}")
        print(f"      examples: {ids[:4]}")

    # B. what should happen to BL_COMPARISON emails that have NO attachment
    print("\nB. TRUE BL_COMPARISON EMAILS WITHOUT ATTACHMENTS: expected status  ->  what we said")
    table = Counter()
    for eid, t in truth.items():
        if t["category"] == "BL_COMPARISON" and not emails[eid]["attachments"]:
            gold = f"{t.get('status')}/{t.get('review_reason')}"
            ours = f"{results[eid]['category'][:5]}:{results[eid]['status']}/{results[eid]['review_reason']}"
            table[(gold, ours)] += 1
    for (gold, ours), n in table.most_common():
        print(f"   {n:3} x  expected {gold:28} we said {ours}")

    # C. review cases we missed or invented
    print("\nC. HUMAN REVIEW: cases where we and the answer file disagree")
    missed, invented = [], []
    for eid, t in truth.items():
        gold_review = t.get("status") == "NEEDS_REVIEW"
        our_review = results[eid]["status"] == "NEEDS_REVIEW"
        if gold_review and not our_review:
            missed.append((eid, t.get("review_reason"), results[eid]["status"]))
        if our_review and not gold_review:
            invented.append((eid, results[eid]["review_reason"], t["category"], t.get("status")))
    print(f"   missed (should go to a person, we did not): {len(missed)}")
    for eid, reason, status in missed[:12]:
        print(f"      {eid}  expected {reason}, we said {status}")
    print(f"   invented (we sent to a person, not needed): {len(invented)}")
    for (reason, cat, status), n in Counter((r, c, s) for _, r, c, s in invented).most_common(6):
        print(f"      {n:3} x we said {reason}; answer file: category {cat}, status {status}")

    # D. defects
    print("\nD. DEFECT FIELDS: emails where our defect fields differ from the answer file")
    shown = 0
    for eid, t in truth.items():
        if t["category"] != "BL_COMPARISON" or t.get("status") == "NEEDS_REVIEW":
            continue
        gold_fields, our_fields = set(t["defect_fields"]), set(results[eid].get("defect_fields") or [])
        if gold_fields != our_fields:
            shown += 1
            print(f"   {eid}: expected {sorted(gold_fields)}, we said {sorted(our_fields)} "
                  f"(status {results[eid]['status']})")
    if not shown:
        print("   none")


if __name__ == "__main__":
    main()