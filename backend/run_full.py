"""Run the whole inbox through the pipeline, write submission.json and score it.

Run it from the repo folder. It can be stopped with Control+C and started again:
answers that were already asked are saved, so nothing is asked (or paid) twice.
    caffeinate -i python -m backend.run_full
"""
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from backend import pipeline
from backend.loader import Inbox
from backend.submission import load_expected_email_ids, write_submission

REPO_ROOT = Path(__file__).resolve().parent.parent
bundles = sorted(REPO_ROOT.parent.glob("sdoc-hac*bundle"))
dockers = sorted(REPO_ROOT.parent.glob("sdoc-hac*docker"))
if not bundles or not (bundles[0] / "inbox").exists():
    raise SystemExit("Could not find the data bundle folder next to the repo")
SOURCE = bundles[0]
SCORER = dockers[0] / "server" / "score_cli.py" if dockers else None

OUT_DIR = REPO_ROOT / "backend" / ".cache"  # ".cache" is ignored by git
RESULTS_FILE = OUT_DIR / "results.json"
SUBMISSION_FILE = OUT_DIR / "submission.json"
CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)


def show_score(report):
    s1, s3, rel, e2e = report["stage1"], report["stage3"], report["reliability"], report["end_to_end"]
    print("\n" + "=" * 60)
    print(f"FINAL SCORE {report['final_score']:.4f}   ({report['n_emails']} emails)")
    print("  = 0.30 x classification macro-F1 + 0.20 x defect F1 + 0.50 x end-to-end")
    print("=" * 60)
    print(f"\nCLASSIFICATION  accuracy {s1['accuracy']:.3f}   macro-F1 {s1['macro_f1']:.3f}")
    for c in CATEGORIES:
        p, r, f = prf(**s1["per"][c])
        print(f"  {c:15} precision {p:.2f}  recall {r:.2f}  f1 {f:.2f}")
    print("\n  confusion (row = true category, column = what we said)")
    print("  " + " " * 15 + "".join(f"{c[:8]:>10}" for c in CATEGORIES))
    for actual in CATEGORIES:
        row = s1["confusion"].get(actual, {})
        print("  " + f"{actual:15}" + "".join(f"{row.get(c, 0):>10}" for c in CATEGORIES))
    print(f"\nDEFECT FIELDS   recall {s3['defect_recall']:.3f}  precision {s3['defect_precision']:.3f}  "
          f"f1 {s3['defect_f1']:.3f}  field-f1 {s3['field_f1']:.3f}")
    print(f"HUMAN REVIEW    recall {rel['escalation_recall']:.3f}  precision {rel['escalation_precision']:.3f}  "
          f"(should be {rel['gold_review']}, we sent {rel['pred_review']})")
    for reason, d in rel["per_reason"].items():
        print(f"  {reason:20} {d['caught']}/{d['total']} sent to a person")
    print(f"END-TO-END      {e2e['success']}/{e2e['total']} defect emails fully right  (rate {e2e['rate']:.3f})")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    emails = Inbox(str(SOURCE)).emails()
    print(f"Running {len(emails)} emails. This can take one to two hours; keep the Mac awake.", flush=True)

    results, errors = {}, {}
    started = time.time()
    try:
        for n, email in enumerate(emails, 1):
            email_id = email["email_id"]
            try:
                results[email_id] = pipeline.process_email(email, SOURCE)
            except Exception as error:  # one bad email must not stop the others
                errors[email_id] = f"{type(error).__name__}: {str(error)[:200]}"
            if n % 10 == 0 or n == len(emails):
                minutes = (time.time() - started) / 60
                print(f"{n}/{len(emails)} done, {len(errors)} errors, {minutes:.1f} min", flush=True)
    except KeyboardInterrupt:
        print("\nStopped by you. Start it again to continue (saved answers are reused).")

    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\nProcessed {len(results)} emails, {len(errors)} errors. Saved {RESULTS_FILE.name}")
    print("categories:", dict(Counter(r["category"] for r in results.values())))
    print("statuses:  ", dict(Counter(r["status"] for r in results.values())))
    print("reasons:   ", dict(Counter(r["review_reason"] for r in results.values() if r["review_reason"])))

    if errors or len(results) < len(emails):
        print("\nNot scored, because some emails failed. First errors:")
        for email_id, message in list(errors.items())[:8]:
            print(f"  {email_id}: {message}")
        print("Start it again (the finished emails cost nothing) or tell me what the errors say.")
        return

    expected_ids = load_expected_email_ids(SOURCE / "sample_submission.json")
    write_submission(results, SUBMISSION_FILE, expected_ids)
    print(f"Wrote {SUBMISSION_FILE}")

    if SCORER is None or not SCORER.exists():
        print("Could not find the official scorer folder next to the repo, so no score.")
        return
    done = subprocess.run([sys.executable, str(SCORER), str(SUBMISSION_FILE), "--json"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        print("The scorer failed:", done.stderr[-500:])
        return
    show_score(json.loads(done.stdout))


if __name__ == "__main__":
    main()