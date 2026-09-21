"""Read text out of SI / BL attachments (txt, pdf, docx, xlsx).

read_attachment() never crashes. It always returns a dict:
    {"text": str, "pages": [str, ...], "status": str, "note": str, "ocr": bool}

status meaning:
    ok          text was read fine
    scanned     a PDF that is only a picture (and the AI could not read it, or ocr=False)
    unreadable  the file is broken or has a format we cannot open
    empty       the file opened but has no text in it

pages   the text page by page (a txt / docx / xlsx file counts as one page)
ocr     True when the text was read from a picture by the AI, so it may have small mistakes
"""
import io
from pathlib import Path

# The scanned files are 150 dpi pictures. Rendering them bigger would add no detail.
OCR_DPI = 150


def _result(text, status, note="", pages=None, ocr=False):
    if pages is None:
        pages = [text] if text else []
    return {"text": text, "pages": pages, "status": status, "note": note, "ocr": ocr}


def _read_txt(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return _result(text, "ok" if text.strip() else "empty")


def _read_pdf(path):
    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
            has_images = any(page.images for page in pdf.pages)
    except Exception as e:
        return _result("", "unreadable", f"PDF could not be opened: {type(e).__name__}")

    text = "\n".join(pages).strip()
    if len(text) < 20:
        if has_images:
            return _result("", "scanned", "PDF has no text layer, only images")
        return _result("", "empty", "PDF has no text")
    return _result(text, "ok", pages=pages)


def _ocr_pdf(path):
    """Read a picture-only PDF with AI vision (Gemini), one page at a time.

    If anything goes wrong the status stays 'scanned', so the pipeline can send it to a person.
    """
    if __package__:
        from backend import llm  # normal package execution from the repository root
    else:
        import llm  # allow: python backend/test_readers.py
    import pdfplumber

    try:
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                buffer = io.BytesIO()
                page.to_image(resolution=OCR_DPI).original.save(buffer, format="PNG")
                pages.append(llm.transcribe_image(buffer.getvalue()))
    except llm.LLMError as e:
        return _result("", "scanned", f"PDF is a picture and the AI could not read it: {e}")
    except Exception as e:
        return _result("", "scanned", f"PDF is a picture and could not be turned into images: {type(e).__name__}")
    return _result("\n".join(pages), "ok", "Read from a picture by AI vision (OCR)", pages=pages, ocr=True)


def _read_docx(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(path)
    except Exception as e:
        return _result("", "unreadable", f"DOCX could not be opened: {type(e).__name__}")

    lines = []
    # Walk the body in order so paragraphs and tables stay in the right place
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            line = Paragraph(child, document).text.strip()
            if line:
                lines.append(line)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, document).rows:
                cells = []
                for cell in row.cells:
                    value = cell.text.strip().replace("\n", " ")
                    if value and value not in cells:  # merged cells repeat
                        cells.append(value)
                if cells:
                    lines.append(" | ".join(cells))

    text = "\n".join(lines)
    return _result(text, "ok" if text.strip() else "empty")


def _read_xlsx(path):
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:
        return _result("", "unreadable", f"XLSX could not be opened: {type(e).__name__}")

    lines = []
    for sheet in workbook.worksheets:
        lines.append(f"## Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
            if cells:
                lines.append("\t".join(cells))

    text = "\n".join(lines)
    return _result(text, "ok" if len(lines) > 1 else "empty")


READERS = {".txt": _read_txt, ".pdf": _read_pdf, ".docx": _read_docx, ".xlsx": _read_xlsx}


def read_attachment(path, ocr=True):
    """Read one attachment file and return {"text", "pages", "status", "note", "ocr"}.

    ocr=True  a picture-only PDF is read by the AI (needs the Gemini key)
    ocr=False nothing goes online, a picture-only PDF is just reported as 'scanned'
    """
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        return _result("", "unreadable", f"Unsupported file type: {path.suffix}")
    if not path.exists():
        return _result("", "unreadable", "File not found")
    try:
        result = reader(path)
    except Exception as e:  # last safety net, never crash the pipeline
        return _result("", "unreadable", f"Unexpected error: {type(e).__name__}")
    if ocr and result["status"] == "scanned":
        result = _ocr_pdf(path)
    return result
