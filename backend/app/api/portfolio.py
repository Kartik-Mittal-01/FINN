import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Announcement, Company, Holding
from ..services import company_discovery as cd, market_data
from ..services.state import is_demo
from .deps import iso

router = APIRouter(prefix="/api", tags=["portfolio"])


class AddIn(BaseModel):
    ticker: str
    kind: str = "portfolio"


def _clean_ticker(t: str) -> str:
    t = re.sub(r"\.(NS|BO)$", "", t.strip().upper())
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", t):
        raise HTTPException(422, "Ticker must be 1-20 characters: letters, digits, & or -")
    return t


@router.get("/portfolio")
def portfolio(db: Session = Depends(get_db)):
    demo = is_demo(db)
    since = datetime.utcnow() - timedelta(hours=24)
    out = []
    for h in db.query(Holding).all():
        co = db.get(Company, h.ticker)
        st = market_data.stats(db, h.ticker)
        anns = db.query(Announcement).filter(Announcement.ticker == h.ticker, Announcement.filed_at >= since, Announcement.is_demo == demo).all()
        out.append({"ticker": h.ticker, "name": co.name if co else h.ticker, "sector": co.sector if co else None, "kind": h.kind,
                    "stats": st, "last_24h": {"critical": sum(a.priority == "critical" for a in anns), "high": sum(a.priority == "high" for a in anns), "total": len(anns)}})
    out.sort(key=lambda x: (x["kind"] != "portfolio", -(x["last_24h"]["critical"] * 100 + x["last_24h"]["high"] * 10), x["ticker"]))
    return {"holdings": out, "mode": "demo" if demo else "live"}


@router.post("/portfolio")
def add_holding(body: AddIn, db: Session = Depends(get_db)):
    if body.kind not in ("portfolio", "watchlist"):
        raise HTTPException(422, "kind must be portfolio or watchlist")
    t = _clean_ticker(body.ticker)
    if db.get(Holding, t):
        raise HTTPException(409, f"{t} is already in your list")
    co, status = cd.resolve_company(db, t)
    db.add(Holding(ticker=t, kind=body.kind))
    db.commit()
    price = None
    if not is_demo(db):
        price = market_data.fetch_live(db, t)
    return {"ticker": t, "name": co.name, "verification": status, "price_fetch": price,
            "note": None if status != "unverified" else "Could not verify this ticker against a live source; it was added anyway."}


@router.delete("/portfolio/{ticker}")
def remove_holding(ticker: str, db: Session = Depends(get_db)):
    h = db.get(Holding, ticker.upper())
    if not h:
        raise HTTPException(404, "Not in your list")
    db.delete(h)
    db.commit()
    return {"removed": ticker.upper()}


@router.get("/portfolio/exposure")
def exposure(db: Session = Depends(get_db)):
    """Equal-weighted sector distribution and aggregate performance of the portfolio (no position sizes are stored)."""
    hs = db.query(Holding).filter_by(kind="portfolio").all()
    sectors: dict[str, int] = {}
    perf = {"day": [], "week": [], "month": []}
    as_of = None
    for h in hs:
        co = db.get(Company, h.ticker)
        sectors[(co.sector if co and co.sector else "Unclassified")] = sectors.get((co.sector if co and co.sector else "Unclassified"), 0) + 1
        st = market_data.stats(db, h.ticker)
        if st.get("available"):
            as_of = max(as_of or st["as_of"], st["as_of"])
            for k, f in (("day", "change_pct"), ("week", "week_pct"), ("month", "month_pct")):
                if st[f] is not None:
                    perf[k].append(st[f])
    n = max(1, len(hs))
    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return {"sectors": sorted([{"sector": k, "count": v, "weight_pct": round(v / n * 100, 1)} for k, v in sectors.items()], key=lambda x: -x["count"]),
            "performance": {"day": avg(perf["day"]), "week": avg(perf["week"]), "month": avg(perf["month"]),
                            "advancers": sum(1 for x in perf["day"] if x > 0), "decliners": sum(1 for x in perf["day"] if x < 0)},
            "weighting": "equal-weighted (position sizes are not tracked in this prototype)", "as_of": as_of, "holdings": len(hs)}


@router.get("/companies/search")
def search_companies(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    ql = q.strip().lower()
    rows = db.query(Company).filter((Company.ticker.ilike(f"%{ql}%")) | (Company.name.ilike(f"%{ql}%"))).limit(12).all()
    held = {h.ticker for h in db.query(Holding).all()}
    res = [{"ticker": c.ticker, "name": c.name, "sector": c.sector, "held": c.ticker in held} for c in rows]
    t = re.sub(r"\.(NS|BO)$", "", q.strip().upper())
    if re.fullmatch(r"[A-Z0-9&\-]{1,20}", t) and not any(r["ticker"] == t for r in res):
        res.append({"ticker": t, "name": f"Use “{t}” as an NSE ticker", "sector": None, "held": t in held, "unverified": True})
    return {"results": res}


@router.get("/market/{ticker}/history")
def history(ticker: str, days: int = 120, db: Session = Depends(get_db)):
    bs = market_data.bars(db, ticker.upper(), min(days, 400))
    return {"ticker": ticker.upper(), "source": "demo" if is_demo(db) else "yfinance", "bars": [
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bs],
        "note": "End-of-day data – not real-time."}


@router.get("/market/{ticker}/stats")
def stats(ticker: str, db: Session = Depends(get_db)):
    return market_data.stats(db, ticker.upper())


@router.post("/market/{ticker}/refresh")
def refresh(ticker: str, db: Session = Depends(get_db)):
    if is_demo(db):
        return {"ok": False, "message": "Demo mode: prices are synthetic. Switch to Live to fetch from Yahoo Finance."}
    return market_data.fetch_live(db, ticker.upper(), force=True)
