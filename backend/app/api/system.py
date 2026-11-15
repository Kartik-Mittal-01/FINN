import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Announcement, Company, Document, Holding, PriceBar
from ..services import alert_engine, announcement_ingestion as ai, demo_seed, embeddings, llm as llm_mod, market_data
from ..services.state import get_mode, is_demo, set_setting

router = APIRouter(prefix="/api/system", tags=["system"])
log = logging.getLogger(__name__)


class ModeIn(BaseModel):
    mode: str


@router.get("/status")
def status(db: Session = Depends(get_db)):
    demo = is_demo(db)
    p = llm_mod.get_llm()
    src = "demo" if demo else "yfinance"
    latest = db.query(func.max(PriceBar.date)).filter(PriceBar.source == src).scalar()
    return {
        "mode": get_mode(db), "server_time": datetime.utcnow().isoformat() + "Z",
        "llm": {"provider": p.name, "model": p.model or None, "available": p.available()},
        "embeddings": embeddings.provider_name(),
        "counts": {"holdings": db.query(Holding).count(), "announcements": db.query(Announcement).filter_by(is_demo=demo).count(),
                   "documents": db.query(Document).filter_by(is_demo=demo).count(), "price_bars": db.query(PriceBar).filter_by(source=src).count()},
        "latest_price_date": latest,
        "demo_loaded": db.query(Announcement).filter_by(is_demo=True).count() > 0,
        "labels": {"demo": "SAMPLE DATA – synthetic, generated for demonstration. Not real prices, filings or reports." if demo else None},
    }


@router.post("/mode")
def set_mode(body: ModeIn, db: Session = Depends(get_db)):
    if body.mode not in ("demo", "live"):
        raise HTTPException(422, "mode must be 'demo' or 'live'")
    set_setting(db, "data_mode", body.mode)
    alert_engine.evaluate(db)
    return {"mode": body.mode}


@router.post("/demo/load")
def load_demo(db: Session = Depends(get_db)):
    """One-click: (re)load the labelled synthetic dataset and switch to demo mode."""
    out = demo_seed.seed_demo(db)
    set_setting(db, "data_mode", "demo")
    return {"loaded": out, "mode": "demo"}


@router.post("/refresh")
def refresh_live(db: Session = Depends(get_db)):
    """Pull end-of-day prices and exchange announcements for all holdings from public live sources."""
    if is_demo(db):
        return {"mode": "demo", "message": "Demo mode uses the bundled synthetic dataset. Switch to Live to fetch real data.", "prices": {}, "announcements": {}}
    tickers = [h.ticker for h in db.query(Holding).all()]
    prices, ok = {}, 0
    for t in tickers:
        r = market_data.fetch_live(db, t, force=True)
        prices[t] = r
        ok += r["ok"]
    end = datetime.utcnow().date()
    codes = {c.ticker: c.bse_code for c in db.query(Company).filter(Company.bse_code.isnot(None)).all()}
    ann = {"nse": ai.ingest(db, ai.NSEConnector(), tickers, end - timedelta(days=7), end)}
    if codes:
        ann["bse"] = ai.ingest(db, ai.BSEConnector(codes), tickers, end - timedelta(days=7), end)
    al = alert_engine.evaluate(db)
    errors = [e for v in ann.values() for e in v["errors"]][:5]
    return {"mode": "live", "prices_ok": ok, "prices_total": len(tickers), "price_errors": {t: r["message"] for t, r in prices.items() if not r["ok"]},
            "announcements": {k: v["ingested"] for k, v in ann.items()}, "announcement_errors": errors, "alerts": al}
