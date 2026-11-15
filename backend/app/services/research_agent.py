"""Evidence-grounded company research. Works for ANY ticker that has primary-source data in the database
(structured financials + indexed annual report / concall PDFs) - nothing here is keyed to the demo companies.

Principles
* Numbers come from the financials table and deterministic calculations (financial_calculations.py). No LLM arithmetic.
* Narrative comes from retrieved excerpts of the company's own documents; every claim carries evidence objects.
* An optional local LLM may paraphrase the business description - rejected if it introduces figures that are not in the
  source text. The rest of the report is deterministic, and says so (`generated_by`).
* Missing data is stated, never filled.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Company, Document, Financial, ResearchReport
from . import company_discovery as cd
from . import financial_calculations as fc
from . import guidance as gd
from . import llm as llm_mod
from . import retrieval
from .state import is_demo

log = logging.getLogger(__name__)
DISCLAIMER = ("Analytical summary of primary-source documents for research purposes. Not investment advice or a recommendation to buy, sell or hold.")


# ------------------------------------------------------------------ data access
def load_fin(db: Session, ticker: str, demo: bool) -> dict:
    rows = db.query(Financial).filter_by(ticker=ticker, is_demo=demo).all()
    annual, quarterly, src, ends = {}, {}, set(), {}
    for r in rows:
        (annual if r.period_type == "annual" else quarterly).setdefault(r.period, {})[r.metric] = r.value
        ends[r.period] = r.period_end
        if r.source:
            src.add(r.source)
    return {"annual": dict(sorted(annual.items(), key=lambda kv: ends[kv[0]])), "quarterly": dict(sorted(quarterly.items(), key=lambda kv: ends[kv[0]])),
            "source": ", ".join(sorted(src)) or None, "source_url": next((r.source_url for r in rows if r.source_url), None)}


def _conf(level: str, reason: str, n: int = 0) -> dict:
    return {"level": level, "reason": reason, "evidence_count": n}


def _fin_ev(label: str, periods: list[str], values: list, source: Optional[str]) -> dict:
    return {"kind": "financial", "label": label, "periods": periods, "values": values, "source": source or "financial statements"}


def _numbers_in(s: str) -> set[str]:
    return {x.replace(",", "").rstrip(".") for x in re.findall(r"\d[\d,]*\.?\d*", s or "")}


class Ctx:
    def __init__(self, db: Session, ticker: str, demo: bool):
        self.db, self.ticker, self.demo = db, ticker.upper(), demo
        self.co = db.get(Company, self.ticker)
        self.fin = load_fin(db, self.ticker, demo)
        self.src = "DEMO – synthetic sample data" if demo else (self.fin["source"] or "financial statements")
        self.docs = db.query(Document).filter_by(ticker=self.ticker, is_demo=demo, status="ready").all()
        self.is_bank = bool(self.fin["annual"]) and all(v.get("ebitda") is None and v.get("debt") is None for v in list(self.fin["annual"].values())[-3:])
        self.fys = list(self.fin["annual"].keys())

    def A(self, fy: str, metric: str):
        return self.fin["annual"].get(fy, {}).get(metric)

    def series(self, metric: str, n: int = 8):
        return [(fy, self.A(fy, metric)) for fy in self.fys[-n:] if self.A(fy, metric) is not None]

    def search(self, q: str, k: int = 3, doc_types=None, **kw):
        return retrieval.search(self.db, self.ticker, q, k=k, is_demo=self.demo, doc_types=doc_types, **kw)


def _clean(o):
    """Make a structure JSON-safe (numpy scalars, NaN)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            return _clean(o.item())
        except Exception:
            return None
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o


# ------------------------------------------------------------------ sections
def _lead_text(text: str, n: int = 3) -> str:
    """First sentences of body prose – skips headings, page banners and short label lines."""
    prose = [l.strip() for l in retrieval.strip_boilerplate(text).splitlines() if len(l.split()) >= 8 and not l.strip().isupper()]
    flat = re.sub(r"\s+", " ", " ".join(prose))
    return " ".join(retrieval.split_sentences(flat)[:n])


def _short(detail: str) -> str:
    return re.sub(r"\s*\([^)]*counts as met\)\.?$", ".", detail)


SEG_LINE = re.compile(r"^(.{3,70}?)\s+[-–:]\s+(\d{1,2}(?:\.\d+)?)\s*%\s*$")


def business(c: Ctx) -> dict:
    ar = retrieval.all_chunks(c.db, c.ticker, c.demo, ["annual_report"])
    segs, seg_cite, desc_by_name = [], None, {}
    for ch, doc in ar:
        lines = [l.strip() for l in ch.text.splitlines()]
        found = [(m.group(1).strip(), float(m.group(2))) for l in lines if (m := SEG_LINE.match(l))]
        if len(found) >= 2 and 85 <= sum(p for _, p in found) <= 115 and not segs:
            segs = [{"name": n, "pct": p} for n, p in found]
            seg_cite = retrieval.Hit(ch.id, doc.id, 1.0, ch.page, ch.text, doc.title, doc.doc_type, doc.period, doc.source_url,
                                     f"/api/documents/{doc.id}/file#page={ch.page}", doc.is_demo).citation()
        for l in lines:
            m = re.match(r"^(.{3,70}?):\s+(.{10,})$", l)
            if m:
                desc_by_name[m.group(1).strip()] = m.group(2).strip().rstrip(".")
    for s in segs:
        s["description"] = desc_by_name.get(s["name"])
    hits = c.search("company business overview segments products services operates", k=3, doc_types=["annual_report"])
    drivers = c.search("key drivers of growth demand volumes pricing mix performance", k=2, doc_types=["annual_report"])
    desc, by = None, "extractive"
    if hits:
        desc = _lead_text(hits[0].text)
        p = llm_mod.get_llm()
        if p.available():
            try:
                src = " ".join(re.sub(r"\s+", " ", retrieval.strip_boilerplate(h.text)) for h in hits)
                out = p.generate("Using ONLY the excerpts below, describe in 2-3 sentences what the company does and how it earns money. Do not add facts or numbers that are not in the excerpts.\n\n" + src,
                                 system="You are a precise financial analyst.", max_tokens=200)
                if out and _numbers_in(out) <= _numbers_in(src):
                    desc, by = out, f"ollama:{p.model}"
            except Exception as e:
                log.info("LLM business summary failed: %s", e)
    ev = [h.citation(i + 1) for i, h in enumerate(hits + drivers)]
    if seg_cite:
        ev.insert(0, {**seg_cite, "n": 0})
    lvl = "high" if segs and hits else "medium" if hits else "none"
    return {"id": "business", "title": "Business snapshot", "description": desc, "description_by": by, "segments": segs,
            "evidence": ev, "confidence": _conf(lvl, "Segment mix and overview read from the annual report." if lvl == "high" else
                                                 "Overview excerpts found; segment mix could not be parsed." if lvl == "medium" else
                                                 "No annual report indexed for this company.", len(ev)),
            "note": None if hits else "No annual-report text available, so the business cannot be described from primary sources."}


def snapshot(c: Ctx) -> dict:
    if not c.fys:
        return {"id": "snapshot", "title": "Financial snapshot", "annual": None, "quarter": None, "confidence": _conf("none", "No financial statements available.")}
    fy = c.fys[-1]
    prev = c.fys[-2] if len(c.fys) > 1 else None
    pprev = c.fys[-3] if len(c.fys) > 2 else None
    g = lambda m: c.A(fy, m)
    pe = c.A(prev, "equity") if prev else None
    pd_ = c.A(prev, "debt") if prev else None
    annual = {
        "period": fy, "revenue": g("revenue"), "ebitda": g("ebitda"), "ebitda_margin": fc.ebitda_margin(g("ebitda"), g("revenue")),
        "pbt": g("pbt"), "pat": g("pat"), "pat_margin": fc.pat_margin(g("pat"), g("revenue")), "debt": g("debt"), "cash": g("cash"),
        "equity": g("equity"), "debt_to_equity": fc.debt_to_equity(g("debt"), g("equity")),
        "roe": fc.roe(g("pat"), g("equity"), pe),
        "roce": fc.roce(g("pbt"), g("finance_cost"), g("equity"), g("debt"), pe, pd_) if g("finance_cost") is not None and g("debt") is not None else None,
        "revenue_yoy": fc.growth(g("revenue"), c.A(prev, "revenue") if prev else None), "pat_yoy": fc.growth(g("pat"), c.A(prev, "pat") if prev else None),
    }
    quarter = None
    if c.fin["quarterly"]:
        qs = list(c.fin["quarterly"].keys())
        q = qs[-1]
        qv = c.fin["quarterly"][q]
        prevq = c.fin["quarterly"].get(qs[-2]) if len(qs) > 1 else None
        yago = c.fin["quarterly"].get(f"{q[:4]}{int(q[4:]) - 1:02d}")
        quarter = {"period": q, "revenue": qv.get("revenue"), "ebitda": qv.get("ebitda"), "pbt": qv.get("pbt"), "pat": qv.get("pat"),
                   "ebitda_margin": fc.ebitda_margin(qv.get("ebitda"), qv.get("revenue")),
                   "revenue_qoq": fc.qoq(qv.get("revenue"), prevq.get("revenue") if prevq else None), "revenue_yoy": fc.yoy(qv.get("revenue"), yago.get("revenue") if yago else None),
                   "pat_qoq": fc.qoq(qv.get("pat"), prevq.get("pat") if prevq else None), "pat_yoy": fc.yoy(qv.get("pat"), yago.get("pat") if yago else None)}
    n_missing = sum(1 for k in ("ebitda", "debt", "cash", "roce") if annual[k] is None)
    notes = []
    if c.is_bank:
        notes.append("EBITDA, debt-to-equity and ROCE are not meaningful for banks/lenders and are not computed.")
    return {"id": "snapshot", "title": "Financial snapshot", "annual": annual, "quarter": quarter, "notes": notes, "source": c.src, "methodology": fc.METHODOLOGY,
            "confidence": _conf("high" if len(c.fys) >= 5 else "medium", f"{len(c.fys)} annual periods of reported data; {n_missing} headline fields unavailable.", len(c.fys))}


def trajectory(c: Ctx) -> dict:
    series = []
    for fy in c.fys[-8:]:
        r, e = c.A(fy, "revenue"), c.A(fy, "ebitda")
        series.append({"period": fy, "revenue": r, "ebitda": e, "pat": c.A(fy, "pat"), "ebitda_margin": fc.ebitda_margin(e, r),
                       "debt": c.A(fy, "debt"), "cfo": c.A(fy, "cfo")})
    hl = []
    for metric, label in (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pat", "PAT")):
        s = c.series(metric)
        if len(s) >= 4:
            first, last = s[-4], s[-1]
            t = fc.trend_label(first[1], last[1], 3)
            cg = fc.cagr(first[1], last[1], 3)
            if cg is not None:
                hl.append({"metric": metric, "label": f"{label} {cg:+.1f}% CAGR, {first[0]}→{last[0]}", "direction": t,
                           "evidence": _fin_ev(f"{label} (₹ cr)", [p for p, _ in s[-4:]], [v for _, v in s[-4:]], c.src)})
    ms = [(p["period"], p["ebitda_margin"]) for p in series if p["ebitda_margin"] is not None]
    if len(ms) >= 4:
        d = ms[-1][1] - ms[-4][1]
        hl.append({"metric": "ebitda_margin", "label": f"EBITDA margin {ms[-4][1]:.1f}% → {ms[-1][1]:.1f}% ({d:+.1f}pp over 3 yrs)",
                   "direction": "growing" if d >= 1 else "deteriorating" if d <= -1 else "stagnant",
                   "evidence": _fin_ev("EBITDA margin (%)", [p for p, _ in ms[-4:]], [v for _, v in ms[-4:]], c.src)})
    lvl = "high" if len(series) >= 6 else "medium" if len(series) >= 3 else "low" if series else "none"
    return {"id": "trajectory", "title": "Financial trajectory", "series": series, "highlights": hl, "source": c.src,
            "confidence": _conf(lvl, f"{len(series)} annual periods plotted.", len(series))}


def balance_sheet(c: Ctx) -> dict:
    if c.is_bank:
        return {"id": "balance_sheet", "title": "Balance sheet", "applicable": False, "series": [], "highlights": [],
                "note": "Leverage and working-capital metrics are not meaningful for banks/lenders (deposits are operating liabilities).",
                "confidence": _conf("low", "Not applicable for lenders.")}
    series = []
    for fy in c.fys[-8:]:
        d, e = c.A(fy, "debt"), c.A(fy, "equity")
        dso, dio, dpo = c.A(fy, "receivable_days"), c.A(fy, "inventory_days"), c.A(fy, "payable_days")
        series.append({"period": fy, "debt": d, "equity": e, "debt_to_equity": fc.debt_to_equity(d, e), "receivable_days": dso, "inventory_days": dio,
                       "payable_days": dpo, "cash_cycle_days": None if None in (dso, dio, dpo) else round(dso + dio - dpo, 1)})
    hl = []
    de = [(p["period"], p["debt_to_equity"]) for p in series if p["debt_to_equity"] is not None]
    direction = None
    if len(de) >= 3:
        d = de[-1][1] - de[-3][1]
        direction = "increasing" if d > 0.05 else "decreasing" if d < -0.05 else "stable"
        hl.append({"label": f"Debt-to-equity {de[-3][1]:.2f} → {de[-1][1]:.2f} over {de[-3][0]}–{de[-1][0]}: leverage {direction}",
                   "evidence": _fin_ev("Debt-to-equity (x)", [p for p, _ in de[-3:]], [v for _, v in de[-3:]], c.src)})
    cc = [(p["period"], p["cash_cycle_days"]) for p in series if p["cash_cycle_days"] is not None]
    if len(cc) >= 3:
        d = cc[-1][1] - cc[-3][1]
        word = ("lengthening – ties up cash" if cc[-1][1] > 0 else "still negative: suppliers fund operations, but narrowing") if d > 3 else "shortening" if d < -3 else "broadly flat"
        hl.append({"label": f"Cash conversion cycle {cc[-3][1]:.0f} → {cc[-1][1]:.0f} days ({word})",
                   "evidence": _fin_ev("Receivable + inventory − payable days", [p for p, _ in cc[-3:]], [v for _, v in cc[-3:]], c.src)})
    last = series[-1] if series else None
    funding = None
    if last and last["debt"] is not None and last["equity"] is not None and (last["debt"] + last["equity"]) > 0:
        tot = last["debt"] + last["equity"]
        funding = {"period": last["period"], "debt_pct": round(last["debt"] / tot * 100, 1), "equity_pct": round(last["equity"] / tot * 100, 1)}
    lvl = "high" if len(de) >= 5 else "medium" if len(de) >= 3 else "low" if de else "none"
    return {"id": "balance_sheet", "title": "Balance sheet", "applicable": True, "series": series, "highlights": hl, "leverage_direction": direction,
            "funding": funding, "source": c.src, "note": "Receivables, inventory and payables are shown as days of sales/cost (standard disclosure), not absolute balances.",
            "confidence": _conf(lvl, f"{len(de)} periods with both debt and equity reported.", len(de))}


def cash_quality(c: Ctx) -> dict:
    if c.is_bank:
        return {"id": "cash_quality", "title": "Cash quality", "applicable": False, "series": [], "highlights": [],
                "note": "Operating cash flow is not a meaningful quality test for banks (loan and deposit flows dominate).", "confidence": _conf("low", "Not applicable for lenders.")}
    series, proxy = [], False
    for fy in c.fys[-8:]:
        pat, cfo, capex = c.A(fy, "pat"), c.A(fy, "cfo"), c.A(fy, "capex")
        inv = c.A(fy, "investing_cf")
        if capex is None and inv is not None:
            capex, proxy = abs(inv), True
        series.append({"period": fy, "pat": pat, "cfo": cfo, "capex": None if capex is None else abs(capex), "fcf": fc.free_cash_flow(cfo, capex),
                       "cfo_to_pat": fc.cfo_to_pat(cfo, pat)})
    hl, verdict = [], None
    last3 = [p for p in series[-3:] if p["pat"] is not None and p["cfo"] is not None]
    if len(last3) >= 2:
        cum = fc.cfo_to_pat(sum(p["cfo"] for p in last3), sum(p["pat"] for p in last3))
        if cum is not None:
            verdict = "converting well" if cum >= 1.0 else "partially converting" if cum >= 0.7 else "weak conversion"
            ratio_txt = f"{cum:.2f}×" if cum <= 5 else ">5× (PAT is small relative to operating cash flow)"
            hl.append({"label": f"Cumulative CFO / PAT over {last3[0]['period']}–{last3[-1]['period']}: {ratio_txt} – profits are {verdict} into operating cash",
                       "evidence": _fin_ev("CFO and PAT (₹ cr)", [p["period"] for p in last3], [[p["cfo"], p["pat"]] for p in last3], c.src)})
    lf = series[-1] if series else None
    if lf and lf["fcf"] is not None:
        hl.append({"label": f"Free cash flow {lf['period']}: ₹{lf['fcf']:,.0f} cr (CFO ₹{lf['cfo']:,.0f} cr − capex ₹{lf['capex']:,.0f} cr)" + (" – positive" if lf["fcf"] > 0 else " – negative: spending exceeds operating cash"),
                   "evidence": _fin_ev("Free cash flow (₹ cr)", [lf["period"]], [lf["fcf"]], c.src)})
    lvl = "high" if len(last3) >= 3 and not proxy else "medium" if len(last3) >= 2 else "low" if last3 else "none"
    note = "FCF = cash flow from operations − capital expenditure."
    if proxy:
        note += " Capex is not separately available; net investing cash flow is used as a proxy (includes investments), so FCF is conservative."
    return {"id": "cash_quality", "title": "Cash quality", "applicable": True, "series": series, "highlights": hl, "verdict": verdict, "note": note, "source": c.src,
            "confidence": _conf(lvl, f"{len(last3)} recent years with both PAT and CFO.", len(last3))}


def guidance_sections(c: Ctx) -> tuple[dict, dict, list]:
    chunks = retrieval.all_chunks(c.db, c.ticker, c.demo, ["concall"])
    items = gd.extract_guidance(chunks)
    rows = gd.narrative_table(items, c.fin) if c.fin["annual"] else []
    explicit = [i for i in items if i["kind"] == "explicit"]
    calls = {i["doc_period"] for i in explicit}
    qual = [i for i in items if i["kind"] == "commentary"]

    def cite(i):
        d = {"doc_id": i["doc_id"], "title": i["doc_title"], "period": i["doc_period"], "page": i["page"], "excerpt": i["text"][:420],
             "url": f"/api/documents/{i['doc_id']}/file#page={i['page']}", "is_demo": i["is_demo"], "doc_type": "concall"}
        return d
    g_items = [{**{k: i[k] for k in ("metric", "fy", "kind", "low", "high", "unit", "is_latest", "text", "doc_period", "doc_date", "page")}, "citation": cite(i)} for i in items]
    lvl = "high" if len(explicit) >= 3 and len(calls) >= 2 else "medium" if explicit else "low" if qual else "none"
    guidance = {"id": "guidance", "title": "Management guidance", "items": g_items,
                "note": ("Explicit = forward-looking statement with a stated number. Qualitative commentary is shown as-is; no numeric target is inferred." if items else
                         "No concall transcripts are indexed for this company, so management guidance cannot be extracted."),
                "confidence": _conf(lvl, f"{len(explicit)} explicit statements across {len(calls)} calls; {len(qual)} qualitative.", len(items))}
    verifiable = [r for r in rows if r["status"] in ("met", "missed")]
    for r in rows:
        r["citation"] = {"doc_id": r["doc_id"], "title": r["doc_title"], "period": r["call_period"], "page": r["page"], "excerpt": r["statement"][:420],
                         "url": f"/api/documents/{r['doc_id']}/file#page={r['page']}", "is_demo": r["is_demo"], "doc_type": "concall"}
    narrative = {"id": "narrative", "title": "Narrative vs numbers", "rows": rows, "source": c.src,
                 "summary": {"met": sum(r["status"] == "met" for r in rows), "missed": sum(r["status"] == "missed" for r in rows),
                             "tracking": sum(r["status"] == "tracking" for r in rows), "pending": sum(r["status"] == "pending" for r in rows),
                             "not_verifiable": sum(r["status"] == "not_verifiable" for r in rows)},
                 "note": "Each row compares what management said (with page citation) to the reported figure. Tolerances are stated in each row.",
                 "confidence": _conf("high" if len(verifiable) >= 3 else "medium" if verifiable else "low" if rows else "none",
                                     f"{len(verifiable)} of {len(rows)} explicit statements could be checked against reported results.", len(rows))}
    return guidance, narrative, rows


def risks_and_flags(c: Ctx) -> dict:
    hits = c.search("key risks and concerns risk management committee", k=3, doc_types=["annual_report"])
    items = []
    for h in hits:
        for line in h.text.splitlines():
            m = re.match(r"^\d+[.)]\s+(.{12,220}?\.)(?:\s|$)", line.strip()) or re.match(r"^\d+[.)]\s+(.{12,160})$", line.strip())
            if m:
                items.append({"text": m.group(1).strip().rstrip("."), "citation": h.citation()})
    if not items:
        items = [{"text": re.sub(r"\s+", " ", retrieval.strip_boilerplate(h.text))[:200] + "…", "citation": h.citation()} for h in hits[:2]]
    flags = []
    ar = retrieval.all_chunks(c.db, c.ticker, c.demo, ["annual_report"])
    for ch, doc in ar:
        flat = re.sub(r"\s+", " ", ch.text)
        cite = retrieval.Hit(ch.id, doc.id, 1.0, ch.page, ch.text, doc.title, doc.doc_type, doc.period, doc.source_url,
                             f"/api/documents/{doc.id}/file#page={ch.page}", doc.is_demo).citation()
        m = re.search(r"contingent liabilit[^.]{0,220}?(?:Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)\s*crore", flat, re.I)
        if m and not any(f["kind"] == "contingent_liabilities" for f in flags):
            amt = float(m.group(1).replace(",", ""))
            eq = c.A(c.fys[-1], "equity") if c.fys else None
            pct = round(amt / eq * 100, 1) if eq else None
            flags.append({"kind": "contingent_liabilities", "label": f"Contingent liabilities ₹{amt:,.0f} cr" + (f" ({pct}% of net worth)" if pct is not None else ""),
                          "status": "watch" if pct is not None and pct >= 5 else "info", "citation": cite})
        m = re.search(r"(unmodified opinion|qualified opinion|adverse opinion|disclaimer of opinion|emphasis of matter|material uncertainty[^.]{0,40}going concern)", flat, re.I)
        if m and not any(f["kind"] == "auditor" for f in flags):
            txt = m.group(1).lower()
            clean = "unmodified" in txt and not re.search(r"qualified opinion|adverse|disclaimer|emphasis|going concern", flat, re.I) or "no qualification" in flat.lower()
            flags.append({"kind": "auditor", "label": "Auditor: unmodified (clean) opinion" if clean else f"Auditor flag: {m.group(1)}", "status": "clean" if clean else "watch", "citation": cite})
        m = re.search(r"related[- ]part(?:y|ies) transactions?[^.]{0,200}?(?:Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)\s*crore", flat, re.I)
        if m and not any(f["kind"] == "rpt" for f in flags):
            flags.append({"kind": "rpt", "label": f"Related-party transactions with promoter group ≈ ₹{float(m.group(1).replace(',', '')):,.0f} cr", "status": "info", "citation": cite})
    lvl = "high" if items and flags else "medium" if items or flags else "none"
    return {"id": "risks", "title": "Risks & accounting flags", "risks": items[:5], "flags": flags,
            "confidence": _conf(lvl, f"{len(items)} management-stated risks, {len(flags)} accounting flags found in the annual report.", len(items) + len(flags)),
            "note": None if (items or flags) else "No annual report is indexed, so no risk disclosures could be read."}


def bull_bear(c: Ctx, narrative_rows: list, risks: dict, traj: dict, bs: dict, cq: dict, snap: dict) -> dict:
    bull, bear = [], []

    def hl(sec, metric):
        return next((h for h in sec.get("highlights", []) if h.get("metric") == metric), None)
    r = hl(traj, "revenue")
    if r:
        (bull if r["direction"] == "growing" else bear if r["direction"] in ("stagnant", "deteriorating") else []).append(
            {"text": r["label"] + (" – top line is compounding." if r["direction"] == "growing" else " – growth has stalled." if r["direction"] == "stagnant" else " – revenue is shrinking."),
             "evidence": [r["evidence"]], "strength": 3 if r["direction"] != "stagnant" else 2})
    m = hl(traj, "ebitda_margin")
    if m and m["direction"] != "stagnant":
        (bull if m["direction"] == "growing" else bear).append({"text": m["label"] + (" – operating leverage is showing through." if m["direction"] == "growing" else " – profitability per rupee of sales is compressing."), "evidence": [m["evidence"]], "strength": 3})
    p = hl(traj, "pat")
    if p and p["direction"] == "deteriorating":
        bear.append({"text": p["label"] + " – bottom line is shrinking.", "evidence": [p["evidence"]], "strength": 3})
    if cq.get("applicable") and cq.get("highlights"):
        h0 = cq["highlights"][0]
        if cq.get("verdict") == "converting well":
            bull.append({"text": h0["label"], "evidence": [h0["evidence"]], "strength": 3})
        elif cq.get("verdict") == "weak conversion":
            bear.append({"text": h0["label"], "evidence": [h0["evidence"]], "strength": 3})
        fcf = next((h for h in cq["highlights"] if h["label"].startswith("Free cash flow")), None)
        if fcf and "negative" in fcf["label"]:
            bear.append({"text": fcf["label"], "evidence": [fcf["evidence"]], "strength": 2})
        elif fcf and "positive" in fcf["label"]:
            bull.append({"text": fcf["label"], "evidence": [fcf["evidence"]], "strength": 2})
    if bs.get("applicable") and bs.get("leverage_direction"):
        h0 = next((h for h in bs["highlights"] if h["label"].startswith("Debt-to-equity")), None)
        if h0:
            last_de = [s["debt_to_equity"] for s in bs["series"] if s["debt_to_equity"] is not None][-1]
            if bs["leverage_direction"] == "decreasing":
                bull.append({"text": h0["label"], "evidence": [h0["evidence"]], "strength": 2})
            elif bs["leverage_direction"] == "increasing" or last_de > 1.0:
                bear.append({"text": h0["label"] + (" – already above 1×." if last_de > 1.0 else ""), "evidence": [h0["evidence"]], "strength": 3 if last_de > 1.0 else 2})
        wc = next((h for h in bs["highlights"] if h["label"].startswith("Cash conversion cycle") and "lengthening – ties up cash" in h["label"]), None)
        if wc:
            bear.append({"text": wc["label"], "evidence": [wc["evidence"]], "strength": 2})
    roce = (snap.get("annual") or {}).get("roce")
    if roce is not None and roce >= 15:
        bull.append({"text": f"ROCE of {roce:.1f}% ({snap['annual']['period']}) – capital is earning well above typical cost of capital.", "evidence": [_fin_ev("ROCE (%)", [snap["annual"]["period"]], [roce], c.src)], "strength": 2})
    firsts = {}
    for x in sorted(narrative_rows, key=lambda r: r["call_date"] or ""):
        firsts.setdefault((x["metric"], x["fy"]), x)   # judge the ORIGINAL promise; later revisions are shown in the table
    uniq = list(firsts.values())
    met = [x for x in uniq if x["status"] == "met"]
    missed = [x for x in uniq if x["status"] == "missed"]
    lagging = [x for x in uniq if x["status"] == "tracking" and "below the guided pace" in x["detail"]]
    for x in lagging[:1]:
        bear.append({"text": f"Running behind guidance – {_short(x['detail'])}", "evidence": [x["citation"]] + ([_fin_ev(x["actual"]["label"], [x["fy"]], [x["actual"]["value"]], c.src)] if x.get("actual") else []), "strength": 2})
    if met:
        bull.append({"text": f"Management delivered on {len(met)} of {len(met) + len(missed)} verifiable guidance items.", "evidence": [x["citation"] for x in met[:2]] + [_fin_ev(x["actual"]["label"], [x["fy"]], [x["actual"]["value"]], c.src) for x in met[:2] if x.get("actual")], "strength": 2})
    for x in missed[:2]:
        bear.append({"text": f"Guidance missed – {_short(x['detail'])}", "evidence": [x["citation"]] + ([_fin_ev(x["actual"]["label"], [x["fy"]], [x["actual"]["value"]], c.src)] if x.get("actual") else []), "strength": 3})
    for f in risks.get("flags", []):
        if f["status"] == "watch":
            bear.append({"text": f["label"] + " – worth reading the related note.", "evidence": [f["citation"]], "strength": 2})
    if risks.get("risks"):
        r0 = risks["risks"][0]
        bear.append({"text": f"Management itself flags: {r0['text']}.", "evidence": [r0["citation"]], "strength": 1})
    bull.sort(key=lambda x: -x["strength"])
    bear.sort(key=lambda x: -x["strength"])
    return {"id": "bull_bear", "title": "Bull vs bear", "bull": bull[:4], "bear": bear[:4],
            "note": ("Every point cites reported figures or the company's own documents. This is a balance-of-evidence view, not a recommendation." if bull or bear else
                     "Not enough primary-source data to build either case."),
            "confidence": _conf("high" if len(bull) + len(bear) >= 6 else "medium" if len(bull) + len(bear) >= 3 else "low" if bull or bear else "none",
                                f"{len(bull)} bull and {len(bear)} bear points with attached evidence.", len(bull) + len(bear))}


# ------------------------------------------------------------------ report
def build_report(db: Session, ticker: str, demo: Optional[bool] = None) -> dict:
    demo = is_demo(db) if demo is None else demo
    c = Ctx(db, ticker, demo)
    coverage = {"annual_periods": c.fys, "quarterly_periods": list(c.fin["quarterly"].keys()),
                "documents": [{"id": d.id, "title": d.title, "type": d.doc_type, "period": d.period, "pages": d.pages, "url": f"/api/documents/{d.id}/file",
                              "source_url": d.source_url, "uploaded": d.uploaded, "is_demo": d.is_demo} for d in sorted(c.docs, key=lambda d: (d.doc_type, d.doc_date or ""))],
                "financial_source": c.src}
    missing = []
    if not c.fys:
        missing.append("No structured financial statements for this company in the current data mode.")
    if not any(d.doc_type == "annual_report" for d in c.docs):
        missing.append("No annual report indexed – business snapshot, risks and accounting flags are unavailable.")
    if not any(d.doc_type == "concall" for d in c.docs):
        missing.append("No earnings-call transcripts indexed – guidance and narrative-vs-numbers are unavailable.")
    status = "insufficient_data" if not c.fys and not c.docs else "partial" if missing else "ok"
    guidance, narrative, rows = guidance_sections(c)
    snap, traj, bs, cq = snapshot(c), trajectory(c), balance_sheet(c), cash_quality(c)
    risks = risks_and_flags(c)
    sections = {"business": business(c), "snapshot": snap, "trajectory": traj, "balance_sheet": bs, "cash_quality": cq, "narrative": narrative,
                "guidance": guidance, "bull_bear": bull_bear(c, rows, risks, traj, bs, cq, snap), "risks": risks}
    report = {"ticker": c.ticker, "company": c.co.name if c.co else c.ticker, "sector": c.co.sector if c.co else None, "status": status,
              "mode": "demo" if demo else "live", "is_demo": demo, "generated_at": datetime.utcnow().isoformat() + "Z", "coverage": coverage, "missing": missing,
              "generated_by": "deterministic extraction + calculations" + (f"; business paragraph by {sections['business']['description_by']}" if sections["business"]["description_by"] != "extractive" else ""),
              "disclaimer": DISCLAIMER,
              "data_label": "SAMPLE DATA – synthetic, generated for demonstration. Not the company's reported figures or documents." if demo else None,
              "sections": sections}
    return _clean(report)


def save_report(db: Session, report: dict) -> ResearchReport:
    db.query(ResearchReport).filter_by(ticker=report["ticker"], is_demo=report["is_demo"]).delete()
    row = ResearchReport(ticker=report["ticker"], payload=report, generated_by=report["generated_by"], is_demo=report["is_demo"])
    db.add(row)
    db.commit()
    return row


def get_cached(db: Session, ticker: str) -> Optional[dict]:
    row = db.query(ResearchReport).filter_by(ticker=ticker.upper(), is_demo=is_demo(db)).order_by(ResearchReport.id.desc()).first()
    return row.payload if row else None


def get_or_build(db: Session, ticker: str) -> dict:
    return get_cached(db, ticker) or save_report(db, build_report(db, ticker)).payload


def run_research(db: Session, ticker: str, refresh: bool = False, progress=None) -> dict:
    """Full workflow: validate -> (live) discover & ingest -> analyse -> persist. In demo mode only synthetic data is used."""
    say = progress or (lambda *a, **k: None)
    ticker = re.sub(r"\.(NS|BO)$", "", ticker.strip().upper())
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", ticker):
        raise ValueError("Ticker must be 1-20 characters: letters, digits, & or -")
    demo = is_demo(db)
    say("validate", "running", "Resolving company")
    co, status = cd.resolve_company(db, ticker)
    say("validate", "done", f"{co.name} ({status})")
    ingest_info = None
    if not demo:
        have = db.query(Financial).filter_by(ticker=ticker, is_demo=False).count() > 0 or db.query(Document).filter_by(ticker=ticker, is_demo=False).count() > 0
        if refresh or not have:
            try:
                ingest_info = cd.discover_and_ingest(db, ticker, progress=say)
            except Exception as e:
                say("discover", "error", str(e)[:200])
                ingest_info = {"error": str(e)[:300]}
    else:
        say("discover", "skipped", "Demo mode – using bundled synthetic dataset")
    say("analyse", "running", "Building evidence-grounded report")
    report = build_report(db, ticker, demo)
    if ingest_info:
        report["ingestion"] = ingest_info
    if demo and report["status"] == "insufficient_data":
        report["missing"].insert(0, "This ticker is not part of the bundled demo dataset. Switch to Live mode (needs internet) to research it from real filings, or upload its annual report / transcripts there.")
    save_report(db, _clean(report))
    say("analyse", "done", report["status"])
    return report
