"""Read text out of SI / BL attachments (txt, pdf, docx, xlsx).

read_attachment() never crashes. It always returns a dict:
    {"text": str, "status": "ok" | "scanned" | "unreadable" | "empty", "note": str}

status meaning:
    ok          text was read fine
    scanned     a PDF that is only a picture (needs OCR or a vision model)
    unreadable  the file is broken or has a format we cannot open
    empty       the file opened but has no text in it
"""
from pathlib import Path


def _result(text, status, note=""):
    return {"text": text, "status": status, "note": note}


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
    return _result(text, "ok")


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


def read_attachment(path):
    """Read one attachment file and return {"text", "status", "note"}."""
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        return _result("", "unreadable", f"Unsupported file type: {path.suffix}")
    if not path.exists():
        return _result("", "unreadable", "File not found")
    try:
        return reader(path)
    except Exception as e:  # last safety net, never crash the pipeline
        return _result("", "unreadable", f"Unexpected error: {type(e).__name__}")
