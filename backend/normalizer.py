"""Normalize extracted SI and Bill of Lading values before comparison.

Gemini may extract the same value with different capitalization, spacing, or
units. These helpers convert those harmless formatting differences into stable
values so the comparison engine does not report false mismatches.
"""

from decimal import Decimal, InvalidOperation
import re
import unicodedata


TEXT_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
}


def is_missing(value):
    """Return True when an extracted value is absent or blank."""
    return value is None or (isinstance(value, str) and not value.strip())


def normalize_text(value):
    """Normalize case, Unicode, punctuation, and repeated whitespace."""
    if is_missing(value):
        return None

    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = "".join(character if character.isalnum() else " " for character in text)
    return " ".join(text.split())


def _first_number(value):
    """Extract the first decimal number from a numeric value or short label."""
    if is_missing(value) or isinstance(value, bool):
        return None

    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = str(value).replace(",", "")

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return Decimal(match.group())
    except InvalidOperation:
        return None


def normalize_container_count(value):
    """Normalize values such as 6, '6 containers', or '6 x 40HQ'."""
    number = _first_number(value)
    if number is None or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def normalize_weight_kg(value):
    """Normalize kilograms and metric-tonne strings to a Decimal in kg."""
    number = _first_number(value)
    if number is None or number < 0:
        return None

    unit_text = str(value).upper() if isinstance(value, str) else ""
    tonne_pattern = r"\b(MT|MTS|TON|TONS|TONNE|TONNES)\b"
    if re.search(tonne_pattern, unit_text):
        number *= Decimal("1000")

    return number.normalize()


def normalize_value(field, value):
    """Normalize one of the seven official SI/BL comparison fields."""
    if field in TEXT_FIELDS:
        return normalize_text(value)
    if field == "container_count":
        return normalize_container_count(value)
    if field == "gross_weight_kg":
        return normalize_weight_kg(value)
    raise ValueError(f"Unsupported comparison field: {field}")
