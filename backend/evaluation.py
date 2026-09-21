"""Quality checks and optional official-server scoring for pipeline results."""

from collections import Counter

from backend.submission import build_submission


def build_quality_report(results, errors=None, *, low_confidence=0.75):
    """Summarise a run without using hidden competition labels."""
    errors = errors or {}
    categories = Counter()
    statuses = Counter()
    review_reasons = Counter()
    low_confidence_ids = []
    comparison_count = evidence_count = verified_evidence_count = 0

    for email_id, result in results.items():
        categories[result.get("category", "<missing>")] += 1
        statuses[result.get("status", "<missing>")] += 1
        if result.get("review_reason"):
            review_reasons[result["review_reason"]] += 1
        if float(result.get("classification_confidence", 1.0)) < low_confidence:
            low_confidence_ids.append(email_id)

        for comparison in result.get("comparisons", []):
            comparison_count += 1
            for side in ("si_evidence", "bl_evidence"):
                evidence = comparison.get(side)
                if evidence and evidence.get("snippet"):
                    evidence_count += 1
                    if evidence.get("verified"):
                        verified_evidence_count += 1

    possible_evidence = comparison_count * 2
    return {
        "processed": len(results),
        "failed": len(errors),
        "categories": dict(categories),
        "statuses": dict(statuses),
        "review_reasons": dict(review_reasons),
        "low_confidence_ids": sorted(low_confidence_ids),
        "evidence": {
            "present": evidence_count,
            "verified": verified_evidence_count,
            "possible": possible_evidence,
            "coverage": evidence_count / possible_evidence if possible_evidence else 1.0,
            "verification_rate": (
                verified_evidence_count / evidence_count if evidence_count else 1.0
            ),
        },
        "errors": dict(errors),
    }


def submit_for_official_score(results, expected_email_ids, submit_fn):
    """Validate official output shape, then send it to an organiser endpoint.

    ``submit_fn`` should be ``Inbox(<http-url>).submit``. Keeping it injectable
    makes the boundary testable and prevents accidental network calls.
    """
    submission = build_submission(results, expected_email_ids)
    return submit_fn(submission)
