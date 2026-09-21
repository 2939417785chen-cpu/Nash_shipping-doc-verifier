"""All AI calls of the project go through this file (Gemini API).

If we ever change the AI provider, only this file needs to change.
Results are saved in backend/.cache/ so the same question is never asked twice.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR.parent / ".env")
CACHE_DIR = BACKEND_DIR / ".cache"  # ".cache" is already in .gitignore

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg"]


class LLMError(Exception):
    """The AI call failed or gave an answer we cannot use."""


_client = None
_model = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY not found. Check your .env file")
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60000))  # give up after 60s
    return _client


def newest_flash_model(names):
    """Pick the highest-version plain flash model, e.g. models/gemini-3.8-flash"""
    best = None
    for name in names:
        match = re.fullmatch(r"models/gemini-(\d+(?:\.\d+)*)-flash", name)
        if match:
            version = tuple(int(x) for x in match.group(1).split("."))
            if best is None or version > best[0]:
                best = (version, name)
    return best[1] if best else None


def _get_model():
    """Use GEMINI_MODEL from .env if set, otherwise pick the newest flash model."""
    global _model
    if _model is None:
        name = os.getenv("GEMINI_MODEL")
        if not name:
            for attempt in range(4):
                try:
                    names = [m.name for m in _get_client().models.list()
                             if "generateContent" in (m.supported_actions or [])]
                    break
                except LLMError:
                    raise
                except Exception as e:
                    if not _is_retryable(e) or attempt == 3:
                        raise LLMError(f"Could not list models: {type(e).__name__}") from e
                    time.sleep(3 * 2 ** attempt)
            name = newest_flash_model(names)
        if not name:
            raise LLMError("No flash model found for this key")
        _model = name.replace("models/", "")
    return _model


def _parse_json(text):
    """Turn the model's answer into a dict, even if it added extra words or code fences."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _is_retryable(error):
    if isinstance(error, json.JSONDecodeError) or "Timeout" in type(error).__name__:
        return True
    message = str(error)
    return any(word in message for word in
               ("429", "500", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE", "timed out"))


_exhausted = set()  # models whose daily quota ran out during this run
_last_call = 0.0    # when the last real Gemini call started


def _wait_turn():
    """The free tier allows 15 calls a minute, so keep a small gap between real calls."""
    global _last_call
    gap = float(os.getenv("GEMINI_MIN_GAP_SECONDS", "4.5"))
    wait = gap - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _fallback_models():
    """Other models to try when the main one has no quota left.

    Set GEMINI_FALLBACK_MODELS in .env, for example gemini-3.1-flash-lite (comma separated).
    """
    names = os.getenv("GEMINI_FALLBACK_MODELS", "")
    return [n.strip().replace("models/", "") for n in names.split(",") if n.strip()]


def _is_quota_error(message):
    return "429" in message or "RESOURCE_EXHAUSTED" in message


def _ask(model, contents):
    """Ask one model, up to 5 tries. Returns the answer as a dict, or raises LLMError."""
    for attempt in range(5):
        try:
            _wait_turn()
            response = _get_client().models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0),
            )
            return _parse_json(response.text)
        except LLMError:
            raise
        except Exception as e:
            if not _is_retryable(e) or attempt == 4:
                raise LLMError(f"AI call failed ({model}): {type(e).__name__}: {str(e)[:150]}") from e
            time.sleep(3 * 2 ** attempt)  # wait 3s, 6s, 12s, 24s
    raise LLMError(f"AI call failed ({model})")


def call_json(prompt, use_cache=True, images=None):
    """Send a prompt (and maybe pictures), get a dict back.

    Answers are cached (the model name is not part of the cache key, so an answer
    stays valid if we switch model; delete backend/.cache to ask everything again).
    If a model has no daily quota left, the next model in GEMINI_FALLBACK_MODELS is used.
    images is a list of (bytes, mime_type), for example [(png_bytes, "image/png")].
    """
    images = images or []
    fingerprint = prompt + "".join(hashlib.sha256(data).hexdigest() for data, _ in images)
    cache_file = CACHE_DIR / (hashlib.sha256(fingerprint.encode()).hexdigest() + ".json")
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text())

    contents = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images] + [prompt]
    models = [m for m in [_get_model()] + _fallback_models() if m not in _exhausted]
    last_error = None
    for model in models:
        try:
            data = _ask(model, contents)
            break
        except LLMError as e:
            last_error = e
            if not _is_quota_error(str(e)):
                raise
            _exhausted.add(model)  # its quota is gone: skip it from now on
    else:
        raise LLMError("All models have used up their quota for now") from last_error

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False))
    return data


# ---------------------------------------------------------------- classify

CLASSIFY_PROMPT = """You sort emails that arrive in the inbox of a shipping documentation team.
Choose exactly one category:

BL_COMPARISON - the sender asks the team to check, verify or compare a Shipping Instruction (SI)
   against a draft Bill of Lading (BL). Usually an SI and a draft BL are attached. If the email
   says they are attached but one is missing, it is still BL_COMPARISON.
SI_REQUEST - the sender asks the team to prepare or issue a new Shipping Instruction / Bill of
   Lading and gives the shipment details in the email. No two documents are being compared.
INVOICE_QUERY - a question about an invoice, charges, payment or billing.
GENERAL - an operational update, report, reminder or notice that needs no SI/BL checking.
SPAM - unsolicited advertising, scams, phishing or prizes.

Important: the subject line can be misleading. Decide mainly from the body and the attachments.

Return only JSON like this:
{{"category": "<one of the five names>", "confidence": <number from 0 to 1>, "reason": "<one short sentence>"}}

EMAIL
From: {sender}
Subject: {subject}
Attachments: {attachments}
Body:
{body}
"""


def classify_email(email):
    """email is one record from the inbox. Returns {"category", "confidence", "reason"}."""
    names = [Path(a).name for a in email.get("attachments", [])] or ["none"]
    prompt = CLASSIFY_PROMPT.format(
        sender=email.get("from", ""), subject=email.get("subject", ""),
        attachments=", ".join(names), body=email.get("body", ""))
    data = call_json(prompt)

    category = str(data.get("category", "")).strip().upper()
    if category not in CATEGORIES:
        raise LLMError(f"Unexpected category from AI: {category!r}")
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"category": category, "confidence": confidence,
            "reason": str(data.get("reason", ""))[:200]}


# ----------------------------------------------------------------- extract

EXTRACT_PROMPT = """Read this {doc_type} document from a shipment and pull out seven fields.
Labels differ between documents, so match by meaning, not by wording.

Fields:
- shipper: company name of the shipper / exporter. Name only, no street address, city or postcode.
  If the text says "X ON BEHALF OF Y", keep both companies in one value: "X ON BEHALF OF Y".
- consignee: company that receives the cargo. It may be labelled Consignee, "To the Order of"
  or similar. Name only, no address.
- notify_party: the notify party. Name only, no address.
- port_of_loading: also called POL or Load Port. Port name and country as written, without
  any code in brackets.
- port_of_discharge: also called POD. Port name and country as written, without any code.
- container_count: how many containers, as a whole number. If there is a total line such as
  "Total Containers: 5 x 40'HC", the answer is 5. If there is no total, count the container rows.
- gross_weight_kg: total gross weight of the whole shipment as a plain number in kilograms
  (no commas). If the weight is in metric tons, multiply by 1000. If only per-container
  weights are listed and there is no total, add them up. Never use net weight.

Rules:
- Copy names exactly as written. Do not fix spelling.
- If a value is really not in the document, use null. Never guess.
- For each field also give "evidence": the short piece of text you read it from.

Return only JSON like this:
{{"shipper": {{"value": "...", "evidence": "..."}}, "consignee": {{"value": "...", "evidence": "..."}}, ...}}
with all seven field names as keys.

DOCUMENT
{text}
"""


def _to_number(value):
    """'131,058 KG' -> 131058, '22.5' -> 22.5, anything else -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.search(r"\d[\d,]*\.?\d*", str(value))
        if not match:
            return None
        number = float(match.group(0).replace(",", ""))
    return int(number) if number == int(number) else number


def extract_fields(text, doc_type):
    """doc_type is "SI" or "BL". Returns {field: {"value": ..., "evidence": "..."}} for all 7 fields."""
    data = call_json(EXTRACT_PROMPT.format(doc_type=doc_type, text=text))
    result = {}
    for field in FIELDS:
        item = data.get(field)
        if not isinstance(item, dict):
            item = {"value": item, "evidence": ""}
        value, evidence = item.get("value"), str(item.get("evidence") or "")[:200]
        if field in ("container_count", "gross_weight_kg"):
            value = _to_number(value)
            if field == "container_count" and value is not None:
                value = int(value)
        elif value is not None:
            value = str(value).strip() or None
        result[field] = {"value": value, "evidence": evidence}
    return result


# -------------------------------------------------------------- read a picture

TRANSCRIBE_PROMPT = """This is one page of a shipping document (a Shipping Instruction or a Bill of Lading),
saved as a picture. Write down all the text on the page exactly as it is written.
- Keep the order and the line breaks.
- For tables, put each row on one line and separate the columns with " | ".
- Do not summarize, translate or correct anything. Keep spelling, numbers and units as they are.
- If a part is too blurry to read, write [unreadable] in its place.

Return only JSON like this: {"text": "<all the text of the page>"}"""


def transcribe_image(png_bytes):
    """OCR with AI vision: give a page as a PNG picture, get the text on it."""
    data = call_json(TRANSCRIBE_PROMPT, images=[(png_bytes, "image/png")])
    text = str(data.get("text", "")).strip()
    if not text:
        raise LLMError("AI returned no text for the picture")
    return text