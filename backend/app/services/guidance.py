"""Management-guidance extraction from concall transcripts + promised-vs-delivered assessment.

Everything is regex over primary-source text, with each statement carrying its document, period and page.
* A statement is EXPLICIT only if it has a forward-looking marker AND a number (range or point) for a recognised metric.
* Forward-looking sentences with no number are kept as QUALITATIVE commentary (capacity / outlook) – never given a made-up target.
* Assessment compares guidance to *reported* financials with tolerances stated in the output; incomplete years are
  'tracking' (H1 data) or 'pending', and anything we cannot verify is 'not_verifiable'.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from . import financial_calculations as fc

FORWARD = re.compile(r"\b(expect|guid(e|ing|ance)|target|aim|anticipat|outlook|forecast|plan(ned|s|ning)?|project|will|on track|revis(e|ed|ing)|reiterat|maintain|continue to|looking at|should)\b", re.I)
FY_PAT = re.compile(r"\bFY\s?'?(\d{2,4})\b", re.I)
PCT = r"(\d{1,3}(?:\.\d+)?)\s*%"
RANGE = rf"{PCT}\s*(?:to|-|–|and)\s*{PCT}"

GROWTH_RANGE = re.compile(rf"(revenue|sales|top[- ]?line|total income)[^.]{{0,80}}?(?:growth|grow)[^.]{{0,60}}?{RANGE}", re.I)
GROWTH_POINT = re.compile(rf"(revenue|sales|top[- ]?line|total income)[^.]{{0,80}}?(?:growth|grow)[^.]{{0,60}}?{PCT}", re.I)
MARGIN_RANGE = re.compile(rf"(ebitda|operating|pat|net profit)\s+margins?[^.]{{0,70}}?{RANGE}", re.I)
MARGIN_POINT = re.compile(rf"(ebitda|operating|pat|net profit)\s+margins?[^.]{{0,70}}?{PCT}", re.I)
CAPEX = re.compile(r"(?:capex|capital expenditure|capital spend)[^.]{0,90}?(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)\s*(lakh crore|crore|cr\b|billion|bn\b|million|mn\b)", re.I)
CAPACITY = re.compile(r"\b(capacity|commission|expansion|new plant|greenfield|brownfield|add(ing)? (capacity|stores|branches))\b", re.I)
OUTLOOK = re.compile(r"\b(outlook|demand|confident|cautious|constructive|stable|pick-?up|stronger)\b", re.I)


def _sentences(text: str) -> list[str]:
    from .retrieval import split_sentences
    return [s for s in split_sentences(text) if len(s) > 25]


def _fy_for(sentence: str, call_date: Optional[str], anchor: int = 0) -> tuple[Optional[str], bool]:
    """Fiscal year the statement refers to: the FY mention nearest the matched metric/verb (a merged header such as
    'Q4 FY25 earnings call' must not override 'For FY26, we expect ...')."""
    ms = list(FY_PAT.finditer(sentence))
    if ms:
        m = min(ms, key=lambda x: min(abs(x.start() - anchor), abs(x.end() - anchor)))
        y = m.group(1)
        return f"FY{y[-2:]}", False
    if call_date:
        try:
            d = date.fromisoformat(call_date)
            fy = d.year + 1 if d.month >= 4 else d.year
            return f"FY{fy % 100:02d}", True
        except ValueError:
            pass
    return None, True


def _to_crore(v: str, unit: str) -> float:
    x, u = float(v.replace(",", "")), unit.lower().strip()
    if "lakh crore" in u:
        return x * 100000
    if u in ("crore", "cr"):
        return x
    return fc.convert_to_crore(x, u)


def extract_guidance(chunks: list[tuple]) -> list[dict]:
    """chunks: [(Chunk, Document)] for concall documents. Returns statements sorted by call date then position."""
    items, seen = [], set()
    for ch, doc in chunks:
        for s in _sentences(ch.text):
            if s in seen:
                continue
            fwd = bool(FORWARD.search(s))
            base = {"text": s, "doc_id": doc.id, "doc_title": doc.title, "doc_period": doc.period, "doc_date": doc.doc_date,
                    "page": ch.page, "chunk_id": ch.id, "is_demo": doc.is_demo}
            rec, anchor = None, 0
            m = GROWTH_RANGE.search(s)
            if m and fwd:
                rec = dict(metric="revenue_growth", low=float(m.group(2)), high=float(m.group(3)), unit="%")
            elif (m := GROWTH_POINT.search(s)) and fwd:
                rec = dict(metric="revenue_growth", low=float(m.group(2)), high=None, unit="%")
            if not rec:
                m = MARGIN_RANGE.search(s)
                if m and fwd:
                    rec = dict(metric="ebitda_margin" if m.group(1).lower() in ("ebitda", "operating") else "pat_margin", low=float(m.group(2)), high=float(m.group(3)), unit="%")
                elif (m := MARGIN_POINT.search(s)) and fwd:
                    rec = dict(metric="ebitda_margin" if m.group(1).lower() in ("ebitda", "operating") else "pat_margin", low=float(m.group(2)), high=None, unit="%")
            if not rec:
                m = CAPEX.search(s)
                if m and fwd:
                    rec = dict(metric="capex", low=_to_crore(m.group(1), m.group(2)), high=None, unit="INR_crore")
            if rec:
                anchor = m.start()
                fy, inferred = _fy_for(s, doc.doc_date, anchor)
                items.append({**base, **rec, "kind": "explicit", "fy": fy, "fy_inferred": inferred})
                seen.add(s)
                continue
            fm = FORWARD.search(s)
            fy, inferred = _fy_for(s, doc.doc_date, fm.start() if fm else 0)
            if fwd and CAPACITY.search(s):
                items.append({**base, "kind": "commentary", "metric": "capacity", "fy": fy, "fy_inferred": inferred, "low": None, "high": None, "unit": None})
                seen.add(s)
            elif fwd and OUTLOOK.search(s):
                items.append({**base, "kind": "commentary", "metric": "outlook", "fy": fy, "fy_inferred": inferred, "low": None, "high": None, "unit": None})
                seen.add(s)
    items.sort(key=lambda i: (i["doc_date"] or "", i["chunk_id"]))
    # mark the latest explicit statement per (metric, fy) so revisions are visible
    latest = {}
    for i in items:
        if i["kind"] == "explicit":
            latest[(i["metric"], i["fy"])] = i
    for i in items:
        i["is_latest"] = i["kind"] == "explicit" and latest.get((i["metric"], i["fy"])) is i
    return items


# ------------------------------------------------------------------ assessment
def _fy_num(p: str) -> int:
    return int(p[2:])


def _annual(fin: dict, fy: str, metric: str):
    return fin["annual"].get(fy, {}).get(metric)


def _h1(fin: dict, fy: str, metric: str):
    q = fin["quarterly"]
    n = fy[2:]
    a, b = q.get(f"Q1FY{n}", {}).get(metric), q.get(f"Q2FY{n}", {}).get(metric)
    return None if a is None or b is None else a + b


def _range_text(low, high, unit="%"):
    return f"{low:g}{unit}" if high is None else f"{low:g}–{high:g}{unit}"


def assess(item: dict, fin: dict) -> dict:
    """Return {'status', 'actual', 'detail'} for one explicit guidance item."""
    fy, metric, low, high = item["fy"], item["metric"], item["low"], item["high"]
    if not fy:
        return {"status": "not_verifiable", "actual": None, "detail": "Guidance does not name a fiscal year."}
    prev_fy = f"FY{_fy_num(fy) - 1:02d}"
    annual_done = fy in fin["annual"]

    if metric == "revenue_growth":
        if annual_done and prev_fy in fin["annual"]:
            g = fc.pct_change(_annual(fin, fy, "revenue"), _annual(fin, prev_fy, "revenue"))
            if g is None:
                return {"status": "not_verifiable", "actual": None, "detail": "Reported revenue unavailable for the comparison."}
            floor = low if high is not None else low - 1.0
            ok = g >= floor
            tol = "at or above the lower end of the range" if high is not None else "within 1pp of the point estimate or better"
            return {"status": "met" if ok else "missed", "actual": {"label": f"{fy} revenue growth", "value": g, "unit": "%"},
                    "detail": f"Guided {_range_text(low, high)}; reported {g:.1f}% ({tol} counts as met)."}
        h1, h1p = _h1(fin, fy, "revenue"), _h1(fin, prev_fy, "revenue")
        g = fc.pct_change(h1, h1p)
        if g is not None:
            floor = low if high is not None else low - 1.0
            return {"status": "tracking", "actual": {"label": f"H1 {fy} revenue growth (YoY)", "value": g, "unit": "%"},
                    "detail": f"{fy} not yet reported. H1 growth {g:.1f}% vs guided {_range_text(low, high)} – {'on course' if g >= floor else 'below the guided pace'}."}
        return {"status": "pending", "actual": None, "detail": f"{fy} results not yet available."}

    if metric == "ebitda_margin":
        if annual_done and _annual(fin, fy, "ebitda") is not None:
            m = fc.ebitda_margin(_annual(fin, fy, "ebitda"), _annual(fin, fy, "revenue"))
            target = low
            ok = m is not None and m >= target - 0.5
            return {"status": "met" if ok else "missed", "actual": {"label": f"{fy} EBITDA margin", "value": m, "unit": "%"},
                    "detail": f"Guided ~{_range_text(low, high)}; reported {m:.1f}% (within 0.5pp of the lower figure counts as met)."}
        h1e, h1r = _h1(fin, fy, "ebitda"), _h1(fin, fy, "revenue")
        m = fc.ebitda_margin(h1e, h1r)
        if m is not None:
            return {"status": "tracking", "actual": {"label": f"H1 {fy} EBITDA margin", "value": m, "unit": "%"},
                    "detail": f"{fy} not yet reported. H1 margin {m:.1f}% vs guided ~{_range_text(low, high)}."}
        return {"status": "not_verifiable" if annual_done else "pending", "actual": None, "detail": "EBITDA not available for this company/period (e.g. banks) or period not yet reported."}

    if metric == "capex":
        cap = _annual(fin, fy, "capex") if annual_done else None
        if cap is not None:
            dev = (abs(cap) - low) / low * 100
            ok = abs(dev) <= 10
            return {"status": "met" if ok else "missed", "actual": {"label": f"{fy} capex", "value": abs(cap), "unit": "INR_crore"},
                    "detail": f"Guided ≈₹{low:,.0f} cr; reported ₹{abs(cap):,.0f} cr ({dev:+.0f}% vs guidance; within ±10% counts as met)."}
        return {"status": "pending" if not annual_done else "not_verifiable", "actual": None,
                "detail": f"{fy} capex not yet reported." if not annual_done else "Capex not available in the structured financials."}

    return {"status": "not_verifiable", "actual": None, "detail": "No deterministic comparison defined for this metric."}


def narrative_table(items: list[dict], fin: dict) -> list[dict]:
    rows = []
    for i in items:
        if i["kind"] != "explicit":
            continue
        a = assess(i, fin)
        rows.append({"metric": i["metric"], "fy": i["fy"], "statement": i["text"], "range": {"low": i["low"], "high": i["high"], "unit": i["unit"]},
                     "call_period": i["doc_period"], "call_date": i["doc_date"], "is_latest": i["is_latest"], "page": i["page"],
                     "doc_id": i["doc_id"], "doc_title": i["doc_title"], "is_demo": i["is_demo"], **a})
    counts = {}
    for r in rows:
        counts[(r["metric"], r["fy"])] = counts.get((r["metric"], r["fy"]), 0) + 1
    for r in rows:
        r["revisions"] = counts[(r["metric"], r["fy"])]
    order = {"revenue_growth": 0, "ebitda_margin": 1, "pat_margin": 2, "capex": 3}
    rows.sort(key=lambda r: (r["fy"] or "", order.get(r["metric"], 9), r["call_date"] or ""))
    return rows
