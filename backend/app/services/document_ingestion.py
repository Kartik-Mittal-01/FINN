"""Download / register documents, extract text, chunk, (optionally) embed, and store. Idempotent by file hash."""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Chunk, Document
from . import embeddings, pdf_extraction

log = logging.getLogger(__name__)
MAX_BYTES = 80 * 1024 * 1024
TARGET_CHARS = 900
OVERLAP_LINES = 1


def _normalise(page_text: str) -> list[str]:
    """Re-join hard-wrapped lines while keeping short lines (headings, list items) intact."""
    out: list[str] = []
    for raw in page_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if out and len(out[-1]) >= 85 and not out[-1].endswith((".", ":", ";")) and not re.match(r"^(\d+[.)]|[-•])\s", line):
            out[-1] = out[-1] + " " + line
        else:
            out.append(line)
    return out


def chunk_pages(pages: list[str], target: int = TARGET_CHARS) -> list[dict]:
    chunks, idx = [], 0
    for pno, text in enumerate(pages, 1):
        lines = _normalise(text)
        buf: list[str] = []
        size = 0
        for line in lines:
            buf.append(line)
            size += len(line) + 1
            if size >= target:
                chunks.append({"page": pno, "idx": idx, "text": "\n".join(buf)})
                idx += 1
                buf = buf[-OVERLAP_LINES:] if OVERLAP_LINES else []
                size = sum(len(x) + 1 for x in buf)
        if buf and (not chunks or chunks[-1]["text"] != "\n".join(buf)) and sum(len(x) for x in buf) > 40:
            chunks.append({"page": pno, "idx": idx, "text": "\n".join(buf)})
            idx += 1
    return chunks


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ingest_pdf(db: Session, *, ticker: str, path: Path, doc_type: str, title: str, period: Optional[str] = None,
               doc_date: Optional[str] = None, source_url: Optional[str] = None, is_demo: bool = False,
               uploaded: bool = False) -> Document:
    path = Path(path)
    digest = sha256_file(path)
    existing = db.query(Document).filter_by(ticker=ticker, sha256=digest).first()
    if existing:
        return existing
    pages = pdf_extraction.extract_pages(path)
    doc = Document(ticker=ticker, doc_type=doc_type, title=title, period=period, doc_date=doc_date, source_url=source_url,
                   local_path=str(path), pages=len(pages), sha256=digest, is_demo=is_demo, uploaded=uploaded,
                   status="ready" if pdf_extraction.has_text_layer(pages) else "failed")
    db.add(doc)
    db.flush()
    if doc.status == "failed":
        log.warning("No text layer in %s (scanned PDF?) – no chunks created", path.name)
        db.commit()
        return doc
    chunks = chunk_pages(pages)
    vecs = embeddings.embed([c["text"] for c in chunks]) if chunks else None
    for i, c in enumerate(chunks):
        db.add(Chunk(doc_id=doc.id, ticker=ticker, page=c["page"], idx=c["idx"], text=c["text"],
                     embedding=vecs[i].tobytes() if vecs is not None else None))
    db.commit()
    log.info("Ingested %s: %d pages, %d chunks", path.name, len(pages), len(chunks))
    return doc


def download_pdf(url: str, ticker: str) -> Path:
    """Download a PDF from a public URL (company IR page / exchange attachment). Validates it is really a PDF."""
    headers = {"User-Agent": settings.user_agent, "Accept": "application/pdf,*/*"}
    folder = settings.documents_dir / ticker.replace("&", "and")
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "_download.tmp"
    total = 0
    with httpx.stream("GET", url, headers=headers, timeout=settings.http_timeout * 3, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for block in r.iter_bytes(1 << 16):
                total += len(block)
                if total > MAX_BYTES:
                    tmp.unlink(missing_ok=True)
                    raise ValueError("document exceeds 80MB limit")
                f.write(block)
    with open(tmp, "rb") as f:
        if f.read(5) != b"%PDF-":
            tmp.unlink(missing_ok=True)
            raise ValueError("URL did not return a PDF")
    final = folder / f"{sha256_file(tmp)[:16]}.pdf"
    shutil.move(str(tmp), final)
    return final


def delete_documents(db: Session, ticker: str, *, is_demo: bool):
    for d in db.query(Document).filter_by(ticker=ticker, is_demo=is_demo).all():
        db.query(Chunk).filter_by(doc_id=d.id).delete()
        db.delete(d)
    db.commit()


def view_url(doc: Document, page: Optional[int] = None) -> str:
    """Link used by citations: the local served copy (always works) opened at the page."""
    return f"/api/documents/{doc.id}/file" + (f"#page={page}" if page else "")
