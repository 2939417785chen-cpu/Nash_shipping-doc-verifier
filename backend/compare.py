"""Compare the fields read from an SI with the fields read from a draft BL.

The SI is the reference. This file has no AI in it: it is plain rules, so the same
input always gives the same answer.
"""
import re
from difflib import SequenceMatcher

FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg"]
NAME_FIELDS = ("shipper", "consignee", "notify_party")
PORT_FIELDS = ("port_of_loading", "port_of_discharge")

# Different ways to write the same company word
WORD_MAP = {"LIMITED": "LTD", "COMPANY": "CO", "CORPORATION": "CORP",
            "INCORPORATED": "INC", "BERHAD": "BHD", "PRIVATE": "PVT"}

LOOKALIKE = 0.80  # names this similar (but not equal) are "too close to call"


def _words(text):
    """Upper case, '&' -> AND, punctuation -> spaces, then a list of words."""
    text = str(text).upper().replace("&", " AND ")
    return re.sub(r"[^A-Z0-9]+", " ", text).split()


def normalize_name(text):
    """'April Far East (M) Sdn. Bhd.' and 'APRIL FAR EAST (M) SDN BHD' give the same key."""
    words = [WORD_MAP.get(w, w) for w in _words(text)]
    return "".join(words)  # no spaces, so 'FZ-LLC', 'FZ LLC' and 'FZLLC' are the same


def normalize_port(text):
    """'NANTONG PORT, JIANGSU, CHINA (CNNTG)' -> ('NANTONG', 'CHINA'). Country may be None."""
    text = re.sub(r"\(.*?\)", " ", str(text))          # drop codes in brackets
    parts = [p for p in text.split(",") if p.strip()]
    if not parts:
        return ("", None)
    city = "".join(w for w in _words(parts[0]) if w != "PORT")
    country = "".join(_words(parts[-1])) if len(parts) > 1 else None
    return (city, country)


def _same_port(si, bl):
    si_city, si_country = normalize_port(si)
    bl_city, bl_country = normalize_port(bl)
    if si_city != bl_city:
        return False
    # If only one side names a country, that is a formatting difference, not an error
    return si_country is None or bl_country is None or si_country == bl_country


def _similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def compare_field(field, si_value, bl_value):
    """Compare one field. Returns {"field","si_value","bl_value","match","confidence"}.

    match is True / False, or None when a value is missing (nobody can judge that).
    confidence is a simple rule, not a statistic:
      1.0  written exactly the same
      0.95 the same after tidying the format
      0.95 clearly different
      0.6  different but look alike (could be a typo or format issue: a person should look)
    """
    result = {"field": field, "si_value": si_value, "bl_value": bl_value,
              "match": None, "confidence": 0.0}
    if si_value is None or bl_value is None:
        return result

    if field in NAME_FIELDS:
        a, b = normalize_name(si_value), normalize_name(bl_value)
        equal, closeness = a == b, _similarity(a, b)
    elif field in PORT_FIELDS:
        equal = _same_port(si_value, bl_value)
        closeness = _similarity("".join(normalize_port(si_value)[0]),
                                "".join(normalize_port(bl_value)[0]))
    elif field == "container_count":
        equal, closeness = int(si_value) == int(bl_value), 0.0
    elif field == "gross_weight_kg":
        equal, closeness = abs(float(si_value) - float(bl_value)) <= 0.5, 0.0
    else:
        raise ValueError(f"Unknown field: {field}")

    result["match"] = equal
    if equal:
        result["confidence"] = 1.0 if si_value == bl_value else 0.95
    else:
        result["confidence"] = 0.6 if closeness >= LOOKALIKE else 0.95
    return result


def compare_fields(si_fields, bl_fields):
    """si_fields / bl_fields are what llm.extract_fields returns: {field: {"value", "evidence"}}.

    Returns
      comparisons      one entry per field (contract format, with si_evidence / bl_evidence)
      defect_fields    fields that are really different
      missing_fields   fields where SI or BL has no value (needs a person)
      uncertain_fields different but look alike (needs a person to decide)
    """
    comparisons, defects, missing, uncertain = [], [], [], []
    for field in FIELDS:
        si, bl = si_fields.get(field, {}), bl_fields.get(field, {})
        item = compare_field(field, si.get("value"), bl.get("value"))
        if si.get("evidence"):
            item["si_evidence"] = {"snippet": si["evidence"]}
        if bl.get("evidence"):
            item["bl_evidence"] = {"snippet": bl["evidence"]}
        comparisons.append(item)

        if item["match"] is None:
            missing.append(field)
        elif item["match"] is False:
            defects.append(field)
            if item["confidence"] < 0.9:
                uncertain.append(field)
    return {"comparisons": comparisons, "defect_fields": defects,
            "missing_fields": missing, "uncertain_fields": uncertain}