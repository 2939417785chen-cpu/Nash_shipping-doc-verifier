"""Locate AI extraction evidence in the pages returned by document readers."""

from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata


def _search_key(value):
    """Normalise layout noise while keeping letters and numbers meaningful."""
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def locate_evidence_page(snippet, pages, *, fuzzy_threshold=0.78):
    """Return a one-based page number and whether the snippet was verified.

    Exact normalised containment is preferred. A conservative line-level fuzzy
    fallback handles minor OCR/LLM punctuation differences. Short evidence is
    not fuzzily matched because it is too easy to place on the wrong page.
    """
    needle = _search_key(snippet)
    if not needle:
        return None, False

    page_texts = list(pages or [])
    for page_number, page in enumerate(page_texts, start=1):
        if needle in _search_key(page):
            return page_number, True

    if len(needle) < 12:
        return None, False

    best_page = None
    best_score = 0.0
    for page_number, page in enumerate(page_texts, start=1):
        candidates = [line for line in str(page or "").splitlines() if line.strip()]
        for candidate in candidates:
            candidate_key = _search_key(candidate)
            if not candidate_key:
                continue
            score = SequenceMatcher(None, needle, candidate_key).ratio()
            if score > best_score:
                best_page, best_score = page_number, score

    if best_score >= fuzzy_threshold:
        return best_page, True
    return None, False


def enrich_field_evidence(fields, reader_result):
    """Add a page and verification flag to every extracted field's evidence.

    ``reader_result`` is compatible with both the current reader and the OCR
    branch: when ``pages`` is not available, the complete text is page 1.
    The input is not mutated so cached LLM output remains reusable.
    """
    enriched = deepcopy(fields)
    pages = reader_result.get("pages") or []
    if not pages and reader_result.get("text"):
        pages = [reader_result["text"]]

    for item in enriched.values():
        if not isinstance(item, dict):
            continue
        raw_evidence = item.get("evidence")
        if isinstance(raw_evidence, dict):
            snippet = str(raw_evidence.get("snippet") or "")
            evidence = dict(raw_evidence)
        else:
            snippet = str(raw_evidence or "")
            evidence = {"snippet": snippet}

        page, verified = locate_evidence_page(snippet, pages)
        page_source = "snippet" if page is not None else None
        if page is None and item.get("value") is not None:
            page, _value_verified = locate_evidence_page(item["value"], pages)
            if page is not None:
                page_source = "value"
        evidence["page"] = page
        evidence["verified"] = verified
        evidence["page_source"] = page_source
        item["evidence"] = evidence
    return enriched
