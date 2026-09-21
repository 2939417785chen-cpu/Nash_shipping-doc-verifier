# Nash Shipping Document Verifier

## Live Demo

https://2939417785chen-cpu-nash-shipping-doc-verifie-frontendapp-8ksdfo.streamlit.app/

Select **Demo examples** in the sidebar — no API key or local setup is required.
The public deployment intentionally excludes the organizer-provided dataset.
Use **Live local dataset** only when running the project locally with the
competition data folder available on your computer.

An AI-assisted Streamlit application that classifies shipping emails, reads
Shipping Instructions and draft Bills of Lading, compares seven required
fields, and sends uncertain cases to human review with source evidence.

## Problem and solution

Shipping operations teams receive comparison requests, new document requests,
invoice questions, general updates, and spam in the same inbox. For a document
comparison, staff must read the Shipping Instruction (SI) and draft Bill of
Lading (BL), then check seven shipment fields manually.

Nash combines Gemini with deterministic Python rules. Gemini interprets
unstructured emails and documents; Python normalizes and compares the official
fields; Streamlit shows the result, source evidence, and cases that require a
person to decide.

## What it does

1. Classifies each email as `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`,
   `GENERAL`, or `SPAM`.
2. Reads TXT, PDF, DOCX, and XLSX attachments. Picture-only PDFs use Gemini OCR.
3. Extracts the shipper, consignee, notify party, ports, container count, and
   gross weight.
4. Returns `OK`, `MISMATCH`, or `NEEDS_REVIEW` using deterministic comparison
   and decision rules.
5. Shows evidence snippets, page numbers, OCR provenance, and warnings in the UI.

## Technical architecture

```text
Inbox JSON and attachments
        ↓
Document readers and Gemini OCR fallback
        ↓
Gemini classification and structured field extraction
        ↓
Deterministic normalization, comparison, and decision rules
        ↓
Streamlit review interface and validated submission JSON
```

Gemini is the cloud AI component. The application caches model results, spaces
API calls, supports a fallback model, and returns `NEEDS_REVIEW` when it cannot
make a dependable decision.

## Validation

- 50 automated tests cover normalization, comparison, decision rules,
  evidence tracing, orchestration, output validation, and UI formatting.
- Demo mode uses saved examples and does not consume Gemini quota.
- Live mode connects the interface to the real processing pipeline.
- A final accuracy score is not claimed until the full dataset is processed
  and checked with the organizer's self-evaluation service.

## Setup

Requires Python 3.12 or later.

### Windows PowerShell

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and use your own Gemini API key:

```env
GEMINI_API_KEY=your_own_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite
GEMINI_MIN_GAP_SECONDS=5
```

Never commit `.env`. Each teammate can use a separate key and quota.

Place the participant dataset beside this repository, or select its location
from the app sidebar. The folder must contain `inbox/`, `attachments/`, and
`sample_submission.json`.

## Run the application

```powershell
python -m streamlit run frontend\app.py
```

Choose one of two modes:

- **Demo examples** uses saved results, makes no Gemini calls, and is the safe
  option for presentations.
- **Live local dataset** runs the real backend and consumes Gemini quota.
  Results are cached, so unchanged prompts and documents are not charged twice.

## Quota-safe workflow

- Test the real pipeline on a small, varied sample before processing all 520 emails.
- Keep at least five seconds between real Gemini calls.
- Changing comparison or decision rules does not require new Gemini calls.
- Changing classification or extraction prompts creates new cache keys and uses quota.
- If every configured model is unavailable, the pipeline returns
  `NEEDS_REVIEW` instead of dropping the email.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Project structure

- `frontend/` — Streamlit review interface and display formatting.
- `backend/llm.py` — Gemini classification, extraction, OCR, caching, and fallback.
- `backend/readers.py` — TXT, PDF, DOCX, XLSX, and scanned-PDF reading.
- `backend/compare.py` — deterministic SI/BL field comparison.
- `backend/decision.py` — official status and review rules.
- `backend/pipeline.py` — end-to-end and batch orchestration.
- `backend/submission.py` — competition submission generation.
- `backend/evaluation.py` — quality reporting and official scoring boundary.
- `tests/` — automated comparison, decision, pipeline, evidence, and UI tests.
