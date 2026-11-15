import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models import Company, Document
from ..services import document_ingestion as di, research_agent as ra
from ..services.state import is_demo

router = APIRouter(prefix="/api", tags=["research"])
log = logging.getLogger(__name__)
JOBS: dict[str, dict] = {}
_lock = threading.Lock()


def _job_progress(key: str):
    def say(step: str, state: str, detail: str = ""):
        with _lock:
            j = JOBS.setdefault(key, {"steps": []})
            for s in j["steps"]:
                if s["step"] == step:
                    s.update(state=state, detail=detail)
                    break
            else:
                j["steps"].append({"step": step, "state": state, "detail": detail})
    return say


def _run(ticker: str, refresh: bool, key: str):
    db = SessionLocal()
    try:
        ra.run_research(db, ticker, refresh=refresh, progress=_job_progress(key))
        with _lock:
            JOBS[key].update(state="done", finished_at=datetime.utcnow().isoformat() + "Z")
    except Exception as e:
        log.exception("research failed for %s", ticker)
        with _lock:
            JOBS[key].update(state="error", error=str(e)[:300])
    finally:
        db.close()


@router.post("/research/{ticker}/run")
def run(ticker: str, bg: BackgroundTasks, refresh: bool = False, db: Session = Depends(get_db)):
    t = re.sub(r"\.(NS|BO)$", "", ticker.strip().upper())
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", t):
        raise HTTPException(422, "Ticker must be 1-20 characters: letters, digits, & or -")
    key = f"{t}:{'demo' if is_demo(db) else 'live'}"
    with _lock:
        if JOBS.get(key, {}).get("state") == "running":
            return {"job": JOBS[key], "key": key}
        JOBS[key] = {"state": "running", "steps": [], "started_at": datetime.utcnow().isoformat() + "Z", "ticker": t}
    bg.add_task(_run, t, refresh, key)
    return {"job": JOBS[key], "key": key}


@router.get("/research/{ticker}/status")
def status(ticker: str, db: Session = Depends(get_db)):
    key = f"{ticker.upper()}:{'demo' if is_demo(db) else 'live'}"
    return {"job": JOBS.get(key), "has_report": ra.get_cached(db, ticker) is not None}


@router.get("/research/{ticker}")
def get_report(ticker: str, db: Session = Depends(get_db)):
    rep = ra.get_cached(db, ticker)
    if not rep:
        return {"status": "not_run", "ticker": ticker.upper(), "mode": "demo" if is_demo(db) else "live"}
    return rep


@router.get("/research/{ticker}/documents")
def docs(ticker: str, db: Session = Depends(get_db)):
    rows = db.query(Document).filter_by(ticker=ticker.upper(), is_demo=is_demo(db)).order_by(Document.doc_type, Document.doc_date).all()
    return {"documents": [{"id": d.id, "title": d.title, "type": d.doc_type, "period": d.period, "pages": d.pages, "status": d.status, "source_url": d.source_url,
                           "url": f"/api/documents/{d.id}/file", "uploaded": d.uploaded, "is_demo": d.is_demo} for d in rows]}


@router.post("/research/{ticker}/upload")
async def upload(ticker: str, file: UploadFile = File(...), doc_type: str = Form("annual_report"), period: Optional[str] = Form(None),
                 title: Optional[str] = Form(None), db: Session = Depends(get_db)):
    """Fallback when automatic discovery fails: attach the company's own annual report / transcript PDF."""
    if is_demo(db):
        raise HTTPException(409, "Uploads are for real documents – switch to Live mode first (demo mode only shows bundled sample data).")
    if doc_type not in ("annual_report", "concall"):
        raise HTTPException(422, "doc_type must be annual_report or concall")
    t = ticker.upper()
    data = await file.read()
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "File is not a PDF")
    if len(data) > di.MAX_BYTES:
        raise HTTPException(413, "PDF exceeds 80MB")
    folder = settings.documents_dir / t.replace("&", "and")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"upload_{re.sub(r'[^A-Za-z0-9._-]', '_', file.filename or 'document.pdf')}"
    path.write_bytes(data)
    if not db.get(Company, t):
        from ..services import company_discovery as cd
        cd.resolve_company(db, t)
    doc = di.ingest_pdf(db, ticker=t, path=path, doc_type=doc_type, title=title or file.filename or "Uploaded document", period=period,
                        source_url=None, is_demo=False, uploaded=True)
    rep = ra.save_report(db, ra.build_report(db, t, False)).payload
    return {"document": {"id": doc.id, "status": doc.status, "pages": doc.pages}, "report_status": rep["status"],
            "warning": None if doc.status == "ready" else "No extractable text (scanned PDF?). OCR is not part of this prototype."}


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d or not d.local_path or not Path(d.local_path).exists():
        raise HTTPException(404, "Document file not found")
    return FileResponse(d.local_path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{Path(d.local_path).name}"'})
