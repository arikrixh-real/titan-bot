import csv
import json
from pathlib import Path


def _read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace"), "ok", None


def _read_csv(path):
    with Path(path).open("r", encoding="utf-8", errors="replace", newline="") as source_file:
        rows = list(csv.DictReader(source_file))
    if not rows:
        return "", "insufficient", "csv had no readable rows"
    lines = []
    for row in rows[:5000]:
        lines.append("; ".join(f"{key}: {value}" for key, value in row.items() if value not in (None, "")))
    return "\n".join(lines), "ok", None


def _read_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as source_file:
        payload = json.load(source_file)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True), "ok", None


def _read_pdf(path):
    reader_cls = None
    try:
        from pypdf import PdfReader

        reader_cls = PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader

            reader_cls = PdfReader
        except Exception as exc:
            return "", "insufficient", f"pdf extraction unavailable: {exc}"

    try:
        reader = reader_cls(str(path))
        pages = []
        for page in reader.pages[:500]:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if not text:
            return "", "insufficient", "pdf library returned no text"
        return text, "ok", None
    except Exception as exc:
        return "", "insufficient", f"pdf extraction failed: {exc}"


def extract_text(path):
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md"}:
            return _read_text(path)
        if suffix == ".csv":
            return _read_csv(path)
        if suffix == ".json":
            return _read_json(path)
        if suffix == ".pdf":
            return _read_pdf(path)
        return "", "unsupported", f"unsupported suffix {suffix}"
    except Exception as exc:
        return "", "error", str(exc)

