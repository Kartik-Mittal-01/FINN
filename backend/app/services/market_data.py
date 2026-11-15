"""End-of-day price & volume: yfinance (live) or synthetic demo bars, cached in SQLite.

We never invent a live price. If yfinance fails, the last cached bars are served with their real `as_of` date and a
status message; if nothing is cached the caller gets an empty result and the UI explains why.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from ..models import FetchMeta, PriceBar, utcnow
from . import financial_calculations as fc
from .state import price_source

log = logging.getLogger(__name__)
CACHE_MINUTES = 30


def yahoo_symbol(ticker: str, exchange: str = "NS") -> str:
    return f"{ticker}.{exchange}"


def fetch_live(db: Session, ticker: str, force: bool = False) -> dict:
    """Download ~6 months of EOD bars from Yahoo Finance and upsert. Returns {'ok', 'message', 'rows'}."""
    key = f"px:{ticker}"
    meta = db.get(FetchMeta, key)
    if meta and not force and meta.status == "ok" and utcnow() - meta.fetched_at < timedelta(minutes=CACHE_MINUTES):
        return {"ok": True, "message": "cached (fetched < 30 min ago)", "rows": 0}
    try:
        import yfinance as yf
        df = pd.DataFrame()
        for exch in ("NS", "BO"):
            df = yf.Ticker(yahoo_symbol(ticker, exch)).history(period="6mo", auto_adjust=False, raise_errors=False)
            if df is not None and not df.empty:
                break
        if df is None or df.empty:
            raise ValueError("Yahoo Finance returned no data (invalid ticker, delisted, or network blocked)")
        rows = 0
        for ts, r in df.iterrows():
            d = pd.Timestamp(ts).date().isoformat()
            if pd.isna(r.get("Close")):
                continue
            bar = db.query(PriceBar).filter_by(ticker=ticker, date=d, source="yfinance").first() or PriceBar(ticker=ticker, date=d, source="yfinance")
            bar.open, bar.high, bar.low, bar.close = (float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]))
            bar.adj_close = float(r.get("Adj Close", r["Close"]))
            bar.volume = float(r.get("Volume", 0) or 0)
            db.add(bar)
            rows += 1
        _meta(db, key, "ok", f"{rows} bars")
        db.commit()
        return {"ok": True, "message": f"{rows} bars from Yahoo Finance", "rows": rows}
    except Exception as e:
        log.warning("Live price fetch failed for %s: %s", ticker, e)
        db.rollback()
        _meta(db, key, "error", str(e)[:300])
        db.commit()
        return {"ok": False, "message": str(e)[:300], "rows": 0}


def _meta(db: Session, key: str, status: str, message: str):
    m = db.get(FetchMeta, key)
    if m is None:
        m = FetchMeta(key=key)
        db.add(m)
    m.status, m.message, m.fetched_at = status, message, utcnow()


def _f(x):
    return None if x is None else float(x)


def bars(db: Session, ticker: str, days: int = 140) -> list[PriceBar]:
    rows = (db.query(PriceBar).filter_by(ticker=ticker, source=price_source(db)).order_by(PriceBar.date.desc()).limit(days).all())
    return rows[::-1]


def stats(db: Session, ticker: str) -> Optional[dict]:
    """Daily/weekly/30d change, 20-day avg volume, volume multiple, volatility – all from stored EOD bars."""
    bs = bars(db, ticker, 260)
    src = price_source(db)
    meta = db.get(FetchMeta, f"px:{ticker}")
    if len(bs) < 2:
        return {"ticker": ticker, "available": False, "source": src,
                "message": (f"Live fetch failed: {meta.message}" if meta and meta.status == "error" else
                    "Not part of the demo dataset – FINN does not generate synthetic prices for it. Switch to Live mode for real end-of-day data." if src == "demo"
                    else "No live price data stored yet – use Refresh (needs internet access to Yahoo Finance).")}
    df = pd.DataFrame([{"date": pd.Timestamp(b.date), "close": b.close, "volume": b.volume} for b in bs]).set_index("date")
    last, prev = df.iloc[-1], df.iloc[-2]
    daily = fc.pct_change(last.close, prev.close)
    wk = fc.pct_change(last.close, df.iloc[-6].close) if len(df) >= 6 else None
    base30 = df[df.index <= df.index[-1] - pd.Timedelta(days=30)]
    m30 = fc.pct_change(last.close, base30.iloc[-1].close) if len(base30) else None
    vd = fc.volume_deviation(last.volume, df["volume"].iloc[:-1].tolist(), 20)
    return {
        "ticker": ticker, "available": True, "source": src, "as_of": df.index[-1].date().isoformat(),
        "fetched_at": (meta.fetched_at.isoformat() + "Z") if meta else None,
        "close": round(float(last.close), 2), "prev_close": round(float(prev.close), 2),
        "change_pct": _f(daily), "week_pct": _f(wk), "month_pct": _f(m30),
        "volume": float(last.volume), "avg_volume_20d": _f(vd["avg"]), "volume_ratio": _f(vd["ratio"]),
        "volatility_30d": fc.annualised_volatility(df["close"].tolist(), 30),
        "spark": [round(float(x), 2) for x in df["close"].tail(30).tolist()],
        "stale_days": (pd.Timestamp(datetime.now().date()) - df.index[-1]).days,
        "note": "End-of-day data – not real-time.",
    }
