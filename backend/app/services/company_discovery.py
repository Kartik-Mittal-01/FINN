"""Company resolution + primary-document discovery.

Discovery uses screener.in as a *navigation* source: it lists links to annual reports and concall transcripts (which
point at company / exchange-hosted PDFs) and exposes standardised multi-year financials. The pull-side analysis then
relies on those underlying documents and on the standardised financial tables - never on news, broker notes, or the
LLM's own knowledge.

NOTE: parse_screener_html() is written against screener.in's public HTML structure and is tested against a fixture that
mimics it. screener.in is blocked in the build sandbox, so it has NOT been exercised against the live site; if the markup
differs, only this parser needs adjusting.
"""
from __future__ import annotations

import logging
import re
from calendar import monthrange
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Company, Document, Financial
from . import document_ingestion as di
from .announcement_extractors import parse_number, quarter_label

log = logging.getLogger(__name__)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

PL_MAP = [(r"^(sales|revenue)\b", "revenue"), (r"^operating profit", "ebitda"), (r"^other income", "other_income"), (r"^interest", "finance_cost"),
          (r"^depreciation", "depreciation"), (r"^profit before tax", "pbt"), (r"^net profit", "pat")]
BS_MAP = [(r"^borrowings?", "debt"), (r"^equity capital", "_eqcap"), (r"^reserves", "_reserves")]
CF_MAP = [(r"^cash from operating", "cfo"), (r"^fixed assets purchased", "capex"), (r"^cash from investing", "investing_cf")]
RAT_MAP = [(r"^debtor days", "receivable_days"), (r"^inventory days", "inventory_days"), (r"^days payable", "payable_days")]


def _col_period(h: str) -> Optional[tuple[str, date]]:
    m = re.match(r"^\s*([A-Za-z]{3})\s+(\d{4})\s*$", h)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    mo, y = MONTHS[m.group(1).lower()], int(m.group(2))
    return m.group(1), date(y, mo, monthrange(y, mo)[1])


def _table_rows(section) -> tuple[list[str], list[tuple[str, list[Optional[float]]]]]:
    tbl = section.find("table") if section else None
    if not tbl:
        return [], []
    heads = [th.get_text(" ", strip=True) for th in tbl.find("thead").find_all("th")][1:] if tbl.find("thead") else []
    rows = []
    for tr in (tbl.find("tbody") or tbl).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        label = re.sub(r"[\s\xa0]*\+?\s*$", "", tds[0].get_text(" ", strip=True).replace("\xa0", " ")).strip()
        rows.append((label, [parse_number(td.get_text(strip=True).replace("%", "")) for td in tds[1:]]))
    return heads, rows


def parse_screener_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    fin: dict[tuple, dict] = {}   # (period, type, end) -> {metric: val}
    is_bank = False

    def put(section_id, mapping, kind):
        nonlocal is_bank
        heads, rows = _table_rows(soup.find("section", id=section_id))
        cols = [_col_period(h) for h in heads]
        for label, vals in rows:
            low = label.lower()
            if low.startswith(("deposits", "financing profit")):
                is_bank = True
            for pat, metric in mapping:
                if re.search(pat, low):
                    for c, v in zip(cols, vals):
                        if not c or v is None:
                            continue
                        _, end = c
                        period = (f"FY{end.year % 100:02d}" if kind == "annual" else quarter_label(end).replace(" ", ""))
                        fin.setdefault((period, kind, end.isoformat()), {})[metric] = v
                    break

    put("profit-loss", PL_MAP, "annual")
    put("quarters", PL_MAP, "quarterly")
    put("balance-sheet", BS_MAP, "annual")
    put("cash-flow", CF_MAP, "annual")
    put("ratios", RAT_MAP, "annual")
    for (p, k, e), m in fin.items():
        if "_eqcap" in m or "_reserves" in m:
            m["equity"] = (m.pop("_eqcap", 0) or 0) + (m.pop("_reserves", 0) or 0)
        if is_bank:
            m.pop("ebitda", None)
            m.pop("debt", None)
    rows = [dict(period=p, period_type=k, period_end=e, metric=metric, value=v) for (p, k, e), m in fin.items() for metric, v in m.items()]

    docs = {"annual_reports": [], "concalls": []}
    sec = soup.find("section", id="documents")
    if sec:
        for h in sec.find_all(["h3", "h2"]):
            title = h.get_text(" ", strip=True).lower()
            ul = h.find_next("ul")
            if not ul:
                continue
            for li in ul.find_all("li"):
                if "annual report" in title:
                    a = li.find("a", href=True)
                    if a:
                        m = re.search(r"(?:financial year|fy)\s*(\d{4})", a.get_text(" ", strip=True), re.I)
                        yr = int(m.group(1)) if m else None
                        docs["annual_reports"].append({"title": a.get_text(" ", strip=True), "url": a["href"], "period": f"FY{yr % 100:02d}" if yr else None})
                elif "concall" in title:
                    d = li.find(string=re.compile(r"[A-Z][a-z]{2}\s+\d{4}"))
                    when = re.search(r"([A-Z][a-z]{2})\s+(\d{4})", d).groups() if d else None
                    link = next((a for a in li.find_all("a", href=True) if "transcript" in a.get_text(" ", strip=True).lower()), None)
                    if link and when:
                        mo, y = MONTHS[when[0].lower()], int(when[1])
                        docs["concalls"].append({"title": f"Earnings call transcript – {when[0]} {y}", "url": link["href"],
                                                 "period": _call_period(mo, y), "date": date(y, mo, 15).isoformat()})
    return {"name": name, "is_bank": is_bank, "financials": rows, "documents": docs}


def _call_period(month: int, year: int) -> str:
    """Heuristic: map the month a call is held to the quarter it discusses (calls follow results by ~1-6 weeks)."""
    if month in (4, 5, 6):
        return f"Q4FY{year % 100:02d}"
    if month in (7, 8, 9):
        return f"Q1FY{(year + 1) % 100:02d}"
    if month in (10, 11, 12):
        return f"Q2FY{(year + 1) % 100:02d}"
    return f"Q3FY{year % 100:02d}"


def fetch_screener(ticker: str) -> dict:
    headers = {"User-Agent": settings.user_agent}
    last = None
    for path in (f"/company/{ticker}/consolidated/", f"/company/{ticker}/"):
        try:
            r = httpx.get("https://www.screener.in" + path, headers=headers, timeout=settings.http_timeout, follow_redirects=True)
            if r.status_code == 200 and "profit-loss" in r.text:
                out = parse_screener_html(r.text)
                out["source_url"] = "https://www.screener.in" + path
                return out
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:150]
    raise RuntimeError(f"screener.in unavailable for {ticker}: {last}")


def resolve_company(db: Session, ticker: str) -> tuple[Company, str]:
    """Return (company, status) where status is 'known' | 'verified_live' | 'unverified'."""
    ticker = ticker.strip().upper()
    co = db.get(Company, ticker)
    if co:
        return co, "known"
    name, sector, status = ticker, None, "unverified"
    try:
        import yfinance as yf
        info = yf.Ticker(f"{ticker}.NS").info or {}
        if info.get("longName") or info.get("shortName"):
            name, sector, status = info.get("longName") or info.get("shortName"), info.get("sector"), "verified_live"
    except Exception as e:
        log.info("Could not verify %s live: %s", ticker, str(e)[:100])
    co = Company(ticker=ticker, name=name, sector=sector, size_bucket="mid", verified=status == "verified_live", is_demo=False)
    db.add(co)
    db.commit()
    return co, status


def store_financials(db: Session, ticker: str, rows: list[dict], source: str, source_url: Optional[str], is_demo: bool = False):
    db.query(Financial).filter_by(ticker=ticker, is_demo=is_demo).delete()
    for r in rows:
        db.add(Financial(ticker=ticker, unit="INR_crore", source=source, source_url=source_url, is_demo=is_demo, **r))
    db.commit()


def discover_and_ingest(db: Session, ticker: str, max_concalls: int = 4, progress=None) -> dict:
    """Live pipeline: screener -> financial tables -> download latest annual report + recent concall transcripts -> index."""
    say = progress or (lambda *a, **k: None)
    say("discover", "running", "Looking up filings on screener.in")
    found = fetch_screener(ticker)
    say("discover", "done", f"{len(found['documents']['annual_reports'])} annual reports, {len(found['documents']['concalls'])} transcripts listed")
    store_financials(db, ticker, found["financials"], "screener.in (standardised from company filings)", found["source_url"])
    say("financials", "done", f"{len({(r['period']) for r in found['financials']})} periods stored")
    co = db.get(Company, ticker)
    if co and found.get("name"):
        co.name = found["name"]
        db.commit()
    ok, failed = [], []
    todo = []
    ars = sorted(found["documents"]["annual_reports"], key=lambda d: d["period"] or "", reverse=True)[:1]
    todo += [("annual_report", d) for d in ars]
    calls = sorted(found["documents"]["concalls"], key=lambda d: d["date"], reverse=True)[:max_concalls]
    todo += [("concall", d) for d in calls]
    say("documents", "running", f"Downloading {len(todo)} documents")
    for doc_type, d in todo:
        try:
            path = di.download_pdf(d["url"], ticker)
            doc = di.ingest_pdf(db, ticker=ticker, path=path, doc_type=doc_type, title=d["title"], period=d.get("period"),
                                doc_date=d.get("date"), source_url=d["url"], is_demo=False)
            (ok if doc.status == "ready" else failed).append({"title": d["title"], "url": d["url"], "reason": None if doc.status == "ready" else "no text layer (scanned PDF)"})
        except Exception as e:
            failed.append({"title": d["title"], "url": d["url"], "reason": str(e)[:140]})
    say("documents", "done", f"{len(ok)} indexed, {len(failed)} failed")
    return {"documents_ok": ok, "documents_failed": failed, "source_url": found["source_url"]}
