"""Announcement ingestion = connectors (where data comes from) + pipeline (what we do with each filing).

Connectors implement `AnnouncementConnector.fetch()` and return raw dicts; swap or add one without touching anything else.
  * NSEConnector  – public NSE corporate-announcements JSON endpoint (cookie-primed session).
  * BSEConnector  – public BSE announcements JSON endpoint (needs the BSE scrip code).
  * DemoConnector – labelled synthetic fixtures (demo mode only). Never presented as live.

NOTE: the NSE/BSE adapters are written against the public endpoint shapes and are *not verifiable from the build
sandbox* (exchange hosts are blocked there). Both sites aggressively rate-limit/anti-bot; expect to tune headers or
cadence. The interface exists so a different feed can replace them in minutes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from urllib.parse import quote_plus
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Announcement, Company, Holding
from . import announcement_classifier as clf
from . import llm as llm_mod
from .announcement_extractors import extract_management_change, extract_results
from .prioritisation import rule_summary, score_announcement

log = logging.getLogger(__name__)
IST_OFFSET = timedelta(hours=5, minutes=30)


class AnnouncementConnector(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, tickers: list[str], start: date, end: date) -> tuple[list[dict], list[str]]:
        """Return (raw_announcements, errors). Raw dict keys: ticker, company_name, headline, body_text, filed_at (naive UTC),
        exchange, source, url, attachment_url."""


class NSEConnector(AnnouncementConnector):
    name = "nse"
    BASE = "https://www.nseindia.com"

    def _client(self) -> httpx.Client:
        c = httpx.Client(timeout=settings.http_timeout, follow_redirects=True, headers={
            "User-Agent": settings.user_agent, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE}/companies-listing/corporate-filings-announcements"})
        c.get(self.BASE + "/")  # prime cookies – NSE rejects cookie-less API calls
        return c

    def fetch(self, tickers, start, end):
        out, errors = [], []
        try:
            client = self._client()
        except Exception as e:
            return [], [f"NSE unreachable: {str(e)[:120]}"]
        with client:
            for t in tickers:
                try:
                    r = client.get(f"{self.BASE}/api/corporate-announcements",
                                   params={"index": "equities", "symbol": t, "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")})
                    r.raise_for_status()
                    for it in r.json() or []:
                        dt = datetime.strptime(it["an_dt"], "%d-%b-%Y %H:%M:%S") - IST_OFFSET
                        out.append(dict(ticker=t, company_name=it.get("sm_name") or t, headline=(it.get("desc") or "").strip(),
                                        body_text=(it.get("attchmntText") or "").strip(), filed_at=dt, exchange="NSE", source="nse",
                                        url=f"{self.BASE}/get-quotes/equity?symbol={t}", attachment_url=it.get("attchmntFile")))
                except Exception as e:
                    errors.append(f"NSE {t}: {str(e)[:100]}")
        return out, errors


class BSEConnector(AnnouncementConnector):
    name = "bse"
    API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

    def __init__(self, codes: dict[str, str]):
        self.codes = codes  # ticker -> BSE scrip code

    def fetch(self, tickers, start, end):
        out, errors = [], []
        headers = {"User-Agent": settings.user_agent, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}
        for t in tickers:
            code = self.codes.get(t)
            if not code:
                continue
            try:
                r = httpx.get(self.API, headers=headers, timeout=settings.http_timeout, params={
                    "pageno": 1, "strCat": -1, "subcategory": -1, "strPrevDate": start.strftime("%Y%m%d"), "strToDate": end.strftime("%Y%m%d"),
                    "strSearch": "P", "strscrip": code, "strType": "C"})
                r.raise_for_status()
                for it in r.json().get("Table", []):
                    dt = datetime.fromisoformat(it["NEWS_DT"].split(".")[0]) - IST_OFFSET
                    att = it.get("ATTACHMENTNAME")
                    out.append(dict(ticker=t, company_name=it.get("SLONGNAME") or t, headline=(it.get("NEWSSUB") or it.get("HEADLINE") or "").strip(),
                                    body_text=(it.get("HEADLINE") or "").strip(), filed_at=dt, exchange="BSE", source="bse",
                                    url=f"https://www.bseindia.com/stock-share-price/x/y/{code}/corp-announcements/",
                                    attachment_url=f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else None))
            except Exception as e:
                errors.append(f"BSE {t}: {str(e)[:100]}")
        return out, errors


class DemoConnector(AnnouncementConnector):
    name = "demo"

    def __init__(self, fins: dict):
        self.fins = fins

    def fetch(self, tickers, start, end):
        from ..demo.generator import build_announcements
        now = datetime.utcnow()
        items = [a for a in build_announcements(now, self.fins) if not tickers or a["ticker"] in tickers]
        return items, []


# ------------------------------------------------------------------ pipeline
def make_uid(raw: dict) -> str:
    key = f"{raw['source']}|{raw['ticker']}|{raw['filed_at'].isoformat()}|{raw['headline'][:120]}"
    return hashlib.sha1(key.encode()).hexdigest()


def _numbers_in(s: str) -> set[str]:
    return {x.replace(",", "") for x in re.findall(r"\d[\d,]*\.?\d*", s or "")}


def llm_summary(headline: str, body: str, extracted: Optional[dict], fallback: dict) -> dict:
    """Optional local-LLM rewrite of what/why/watch. Rejected (rules summary kept) if it introduces numbers not in the source."""
    p = llm_mod.get_llm()
    if not p.available():
        return fallback
    src = f"{headline}\n{(body or '')[:2500]}\n{json.dumps(extracted)[:1500] if extracted else ''}"
    try:
        raw = p.generate(
            "Summarise this stock-exchange filing for an investor in three short fields. Use ONLY facts from the filing; do not add numbers "
            "or opinions; no buy/sell advice. JSON keys: what (1 sentence), why (1 sentence on why an investor should care), watch (1 sentence on what to monitor next).\n\n" + src,
            system="You write terse, factual investor briefings. Output JSON only.", json_mode=True, max_tokens=260)
        d = json.loads(raw)
        text = " ".join(str(d.get(k, "")) for k in ("what", "why", "watch"))
        if not _numbers_in(text) <= _numbers_in(src) | {"1", "2", "3"}:
            log.info("LLM summary rejected: introduced figures not in source")
            return fallback
        if all(d.get(k) for k in ("what", "why", "watch")):
            return {"what": d["what"], "why": d["why"], "watch": d["watch"], "by": f"ollama:{p.model}"}
    except Exception as e:
        log.info("LLM summary failed: %s", e)
    return fallback


def process_and_store(db: Session, raw: dict, *, size_bucket: str = "large", in_portfolio: bool = True, use_llm: bool = True) -> Announcement:
    uid = make_uid(raw)
    headline, body = raw["headline"], raw.get("body_text") or ""
    c = clf.classify(headline, body, use_llm=use_llm)
    extracted = None
    if c.category == "results":
        extracted = extract_results(body)
        if (not extracted or not extracted.get("metrics")) and raw.get("attachment_url") and raw["source"] != "demo":
            extracted = _results_from_attachment(raw["attachment_url"], raw["ticker"]) or extracted
        if extracted and not extracted.get("metrics"):
            extracted = extracted if extracted.get("notes") else None
    elif c.category == "management_change":
        extracted = extract_management_change(headline, body)
        if extracted:
            for ch in extracted["changes"]:
                q = f"{ch['person']} {raw.get('company_name', raw['ticker'])}"
                ch["profile_search_url"] = "https://www.google.com/search?q=" + quote_plus(q + " linkedin")  # manual lookup link – we do not scrape LinkedIn
    pr = score_announcement(category=c.category, headline=headline, body=body, size_bucket=size_bucket,
                            in_portfolio=in_portfolio, extracted=extracted)
    summ = rule_summary(c.category, headline, raw.get("company_name") or raw["ticker"], extracted)
    if use_llm and c.category not in ("unclassified",):
        summ = llm_summary(headline, body, extracted, summ)
    row = db.query(Announcement).filter_by(uid=uid).first() or Announcement(uid=uid)
    row.ticker, row.company_name, row.headline, row.body_text = raw["ticker"], raw.get("company_name"), headline, body
    row.filed_at, row.exchange, row.source = raw["filed_at"], raw.get("exchange"), raw["source"]
    row.url, row.attachment_url = raw.get("url"), raw.get("attachment_url")
    row.category, row.category_confidence, row.classifier, row.classifier_reasons = c.category, c.confidence, c.classifier, c.reasons
    row.priority, row.attention_score, row.score_reasons = pr["priority"], pr["attention_score"], pr["reasons"]
    row.summary_what, row.summary_why, row.summary_watch, row.summary_by = summ["what"], summ["why"], summ["watch"], summ["by"]
    row.extracted = extracted
    row.is_demo = raw["source"] == "demo"
    db.add(row)
    db.commit()
    return row


def _results_from_attachment(url: str, ticker: str) -> Optional[dict]:
    try:
        from .document_ingestion import download_pdf
        from .pdf_extraction import extract_pages
        path = download_pdf(url, ticker)
        text = "\n".join(extract_pages(path)[:6])
        res = extract_results(text)
        if res:
            res.setdefault("notes", []).append("Extracted from the filing's PDF attachment; verify against the original.")
        return res
    except Exception as e:
        log.info("Attachment extraction failed for %s: %s", url, e)
        return None


def ingest(db: Session, connector: AnnouncementConnector, tickers: list[str], start: date, end: date) -> dict:
    raws, errors = connector.fetch(tickers, start, end)
    companies = {c.ticker: c for c in db.query(Company).filter(Company.ticker.in_({r["ticker"] for r in raws} or {""})).all()}
    held = {h.ticker: h.kind for h in db.query(Holding).all()}
    n = 0
    for raw in raws:
        co = companies.get(raw["ticker"])
        process_and_store(db, raw, size_bucket=(co.size_bucket if co and co.size_bucket else "large"),
                          in_portfolio=held.get(raw["ticker"]) == "portfolio")
        n += 1
    return {"ingested": n, "errors": errors, "connector": connector.name}
