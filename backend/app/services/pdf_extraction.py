"""PDF -> per-page text. PyMuPDF first (fast), pdfplumber as a fallback for awkward PDFs.
Scanned/image-only PDFs yield no text; we report that instead of pretending (OCR is out of scope for the prototype)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def extract_pages(path: str | Path) -> list[str]:
    path = str(path)
    pages: list[str] = []
    try:
        import pymupdf as fitz
    except ImportError:  # older PyMuPDF
        import fitz  # type: ignore
    try:
        with fitz.open(path) as doc:
            pages = [p.get_text("text") for p in doc]
    except Exception as e:
        log.warning("PyMuPDF failed on %s: %s", path, e)
    total = sum(len(p.strip()) for p in pages)
    if not pages or total < 30 * max(1, len(pages)) * 0.2:
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                alt = [(p.extract_text() or "") for p in pdf.pages]
            if sum(len(p.strip()) for p in alt) > total:
                pages = alt
        except Exception as e:
            log.warning("pdfplumber failed on %s: %s", path, e)
    return pages


def has_text_layer(pages: list[str]) -> bool:
    return sum(len(p.strip()) for p in pages) > 100
