"""Research copilot: answers ONLY from retrieved primary-document passages and structured financials.

Flow: detect intent -> gather structured facts (deterministic) + retrieve passages -> compose answer.
  * Without an LLM the answer is assembled deterministically from the facts (always works, always cited).
  * With a local LLM (Ollama) the model rewrites the answer from the numbered sources only; the result is rejected and
    replaced by the deterministic answer if it cites a source that doesn't exist or contains a figure not present in the
    sources. Output is labelled with how it was generated.
  * No evidence -> an explicit 'insufficient evidence' reply. The model's own knowledge of the company is never used.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from . import llm as llm_mod
from . import research_agent as ra
from . import retrieval
from .state import is_demo

log = logging.getLogger(__name__)

INTENTS = [
    ("calls_diff", r"what changed|changed between|last two (earnings )?calls?|between (the )?(last )?two|difference between.*calls?"),
    ("quarters", r"last (four|4) quarters|quarterly|compare.*quarters?|last (few )?quarters"),
    ("guidance", r"guidance|guided|promis|achiev|deliver|\bmet\b|missed|on track|target"),
    ("risks", r"\brisks?\b|concern|worr|red flag|contingent|auditor|related[- ]party"),
    ("cash", r"cash|fcf|\bcfo\b|keeping pace|conversion"),
    ("debt", r"debt|leverage|borrow|balance sheet|\bd/e\b|working capital"),
    ("outlook", r"capacity|expansion|outlook|demand|expect|plans?\b|future|going forward"),
    ("margin", r"margin|ebitda|profitab"),
    ("business", r"earn|segment|what does|business|source[s]? of revenue|revenue mix|primarily|make money"),
    ("growth", r"revenue|sales|growth|trajectory|trend|\bpat\b|profit"),
]
SUGGESTIONS = ["What does the company primarily earn its revenue from?", "Why did the EBITDA margin change?", "Has management achieved its previous growth guidance?",
               "Is cash flow keeping pace with PAT?", "What are the biggest risks in the latest annual report?", "Compare the last four quarters",
               "What changed between the last two earnings calls?"]


class Cites:
    def __init__(self):
        self.items: list[dict] = []
        self._keys: dict = {}

    def add(self, cite: dict, key=None) -> int:
        key = key or (cite.get("doc_id"), cite.get("page"), cite.get("label"), cite.get("excerpt", "")[:40])
        if key in self._keys:
            return self._keys[key]
        n = len(self.items) + 1
        self.items.append({**cite, "n": n})
        self._keys[key] = n
        return n

    def fin(self, ev: dict) -> int:
        return self.add({"kind": "financial", "title": f"Financial statements – {ev['source']}", "label": ev["label"], "periods": ev["periods"], "values": ev["values"],
                         "is_demo": "DEMO" in (ev["source"] or "")}, key=("fin", ev["label"], tuple(ev["periods"])))

    def doc(self, c: dict) -> int:
        return self.add({"kind": "excerpt", **c})


FOLLOW_UP = re.compile(r"^(and|also|but|so|what about|how about|why|how come|can you|could you|please)\b|\b(it|that|those|these|this|them|they|same|previous|earlier|above|more|detail|elaborate|explain|break (it|that) down|which (one|quarter|year))\b", re.I)


def detect_intent(q: str, prev: Optional[str] = None) -> Optional[str]:
    ql = q.lower()
    for name, pat in INTENTS:
        if re.search(pat, ql):
            return name
    # Inherit the previous topic only for a genuine follow-up (elliptical or referring back), never for a fresh unrelated question.
    return prev if prev and FOLLOW_UP.search(ql) and len(q.split()) <= 9 or (prev and len(q.split()) <= 3) else None


def _fmtv(v, unit=""):
    return "n/a" if v is None else f"{v:,.1f}{unit}" if abs(v) < 1000 and not float(v).is_integer() else f"{v:,.0f}{unit}"


def _numbers_in(s: str) -> set[str]:
    return {x.replace(",", "").rstrip(".") for x in re.findall(r"\d[\d,]*\.?\d*", s or "")}


def _sentence_with(text: str, *patterns: str) -> Optional[str]:
    """First sentence matching ALL patterns."""
    flat = re.sub(r"\s+", " ", retrieval.strip_boilerplate(text))
    for s in retrieval.split_sentences(flat):
        if all(re.search(p, s, re.I) for p in patterns):
            return s
    return None


# ------------------------------------------------------------------ intent handlers -> (lines, table)
def _h_business(db, t, demo, rep, q, cz):
    b = rep["sections"]["business"]
    lines = []
    if b["segments"]:
        n = cz.add(b["evidence"][0]) if b["evidence"] and b["evidence"][0].get("n") == 0 else None
        mix = ", ".join(f"{s['name']} {s['pct']:g}%" for s in b["segments"])
        lines.append(f"The company reports its business in these segments (revenue mix): {mix}." + (f" [{n}]" if n else ""))
    elif b["description"]:
        hit = b["evidence"][0] if b["evidence"] else None
        lines.append(f"{b['description']}" + (f" [{cz.doc(hit)}]" if hit else ""))
    return lines, None


def _h_margin(db, t, demo, rep, q, cz):
    tr = rep["sections"]["trajectory"]
    h = next((x for x in tr["highlights"] if x["metric"] == "ebitda_margin"), None)
    lines = []
    if h:
        lines.append(f"{h['label']} [{cz.fin(h['evidence'])}].")
    hits = retrieval.search(db, t, "EBITDA margin was compared with previous year due to", k=4, is_demo=demo, doc_types=["annual_report", "concall"])
    for hit in hits:
        s = _sentence_with(hit.text, r"margin", r"due to|driven by|because|attribut|on account|reflect")
        if s:
            lines.append(f"The company's own explanation: “{s}” [{cz.doc(hit.citation())}]")
            break
    else:
        if h:
            lines.append("The indexed documents do not give an explicit reason for the margin movement, so I won't speculate on the cause.")
    if not h and not lines:
        lines.append("EBITDA margin is not available for this company (it may be a bank, or data is missing).")
    return lines, None


def _h_cash(db, t, demo, rep, q, cz):
    cq = rep["sections"]["cash_quality"]
    if not cq.get("applicable", True):
        return [cq["note"]], None
    lines = [f"{h['label']} [{cz.fin(h['evidence'])}]." for h in cq["highlights"]]
    table = {"columns": ["Period", "PAT", "CFO", "Capex", "FCF", "CFO/PAT"], "unit": "₹ crore",
             "rows": [[s["period"], s["pat"], s["cfo"], s["capex"], s["fcf"], s["cfo_to_pat"]] for s in cq["series"][-5:]]}
    return lines, table


def _h_debt(db, t, demo, rep, q, cz):
    bs = rep["sections"]["balance_sheet"]
    if not bs.get("applicable", True):
        return [bs["note"]], None
    lines = [f"{h['label']} [{cz.fin(h['evidence'])}]." for h in bs["highlights"]]
    if bs.get("funding"):
        f = bs["funding"]
        lines.append(f"Funding mix ({f['period']}): {f['debt_pct']}% debt, {f['equity_pct']}% equity (of debt + equity).")
    table = {"columns": ["Period", "Debt", "Equity", "D/E", "Cash cycle (days)"], "unit": "₹ crore",
             "rows": [[s["period"], s["debt"], s["equity"], s["debt_to_equity"], s["cash_cycle_days"]] for s in bs["series"][-5:]]}
    return lines, table


def _h_risks(db, t, demo, rep, q, cz):
    r = rep["sections"]["risks"]
    lines = [f"{i + 1}. {x['text']} [{cz.doc(x['citation'])}]" for i, x in enumerate(r["risks"][:3])]
    for f in r["flags"]:
        lines.append(f"{f['label']} [{cz.doc(f['citation'])}]")
    return (["Risks the company itself discloses in its annual report:"] + lines) if lines else [], None


def _h_guidance(db, t, demo, rep, q, cz):
    rows = rep["sections"]["narrative"]["rows"]
    if not rows:
        return [], None
    lines = []
    for r in rows:
        n = cz.doc(r["citation"])
        act = r.get("actual")
        a = ("no reported figure yet" if not act else f"{act['label']} {act['value']:.1f}%" if act["unit"] == "%" else f"{act['label']} ₹{act['value']:,.0f} cr")
        lines.append(f"{r['fy']} {r['metric'].replace('_', ' ')} (said on {r['call_period']} call): guided {_rng(r['range'])}; {a} → {r['status'].replace('_', ' ')} [{n}]")
    s = rep["sections"]["narrative"]["summary"]
    head = f"Of management's explicit numeric statements: {s['met']} met, {s['missed']} missed, {s['tracking']} still tracking, {s['pending']} pending."
    table = {"columns": ["FY", "Metric", "Call", "Guided", "Assessment"], "unit": "",
             "rows": [[r["fy"], r["metric"].replace("_", " "), r["call_period"], _rng(r["range"]), r["status"]] for r in rows]}
    return [head] + lines[:8], table


def _rng(r):
    if r["unit"] != "%":
        return f"₹{r['low']:,.0f} cr"
    return f"{r['low']:g}%" if r["high"] is None else f"{r['low']:g}–{r['high']:g}%"


def _h_quarters(db, t, demo, rep, q, cz):
    fin = ra.load_fin(db, t, demo)["quarterly"]
    qs = list(fin.keys())[-4:]
    if len(qs) < 2:
        return [], None
    rows, lines = [], []
    for i, p in enumerate(qs):
        v = fin[p]
        prev = fin[qs[i - 1]] if i else None
        rows.append([p, v.get("revenue"), v.get("ebitda"), v.get("pat"), (round(v["ebitda"] / v["revenue"] * 100, 1) if v.get("ebitda") and v.get("revenue") else None)])
    ev = {"label": "Quarterly revenue, EBITDA, PAT (₹ cr)", "periods": qs, "values": [r[1:4] for r in rows], "source": "DEMO – synthetic sample data" if demo else "financial statements"}
    first, last = fin[qs[0]], fin[qs[-1]]
    from . import financial_calculations as fc
    g = fc.pct_change(last.get("revenue"), first.get("revenue"))
    gp = fc.growth(last.get("pat"), first.get("pat"))
    lines.append(f"Across {qs[0]}–{qs[-1]}, revenue moved from ₹{first.get('revenue'):,.0f} cr to ₹{last.get('revenue'):,.0f} cr ({g:+.1f}%)" + (f" and PAT {gp['pct']:+.1f}%" if gp["pct"] is not None else (f"; PAT growth is {gp['note']}")) + f" [{cz.fin(ev)}].")
    table = {"columns": ["Quarter", "Revenue", "EBITDA", "PAT", "EBITDA margin %"], "unit": "₹ crore", "rows": rows}
    return lines, table


def _h_calls_diff(db, t, demo, rep, q, cz):
    items = rep["sections"]["guidance"]["items"]
    periods = sorted({i["doc_period"] for i in items if i.get("doc_date")}, key=lambda p: next(i["doc_date"] for i in items if i["doc_period"] == p))
    if len(periods) < 2:
        return [], None
    a, b = periods[-2], periods[-1]
    lines = [f"Comparing the {b} call with the {a} call:"]
    by = lambda p: {(i["metric"], i["fy"]): i for i in items if i["doc_period"] == p and i["kind"] == "explicit"}
    A, B = by(a), by(b)
    rows = []
    for k in sorted(set(A) | set(B)):
        x, y = A.get(k), B.get(k)
        label = f"{k[1]} {k[0].replace('_', ' ')}"
        if x and y:
            same = (x["low"], x["high"]) == (y["low"], y["high"])
            lines.append(f"{label}: {_rng2(x)} → {_rng2(y)} ({'unchanged' if same else 'revised'}) [{cz.doc(x['citation'])}][{cz.doc(y['citation'])}]")
            rows.append([label, _rng2(x), _rng2(y), "unchanged" if same else "revised"])
        elif y:
            lines.append(f"{label}: newly guided at {_rng2(y)} [{cz.doc(y['citation'])}]")
            rows.append([label, "—", _rng2(y), "new"])
        else:
            lines.append(f"{label}: guided {_rng2(x)} on the {a} call; not restated on the {b} call [{cz.doc(x['citation'])}]")
            rows.append([label, _rng2(x), "—", "not restated"])
    qa = [i for i in items if i["doc_period"] == b and i["kind"] == "commentary"][:2]
    for i in qa:
        lines.append(f"Qualitative ({i['metric']}) on {b}: “{i['text']}” [{cz.doc(i['citation'])}]")
    return lines, {"columns": ["Item", a, b, "Change"], "unit": "", "rows": rows}


def _rng2(i):
    return _rng({"low": i["low"], "high": i["high"], "unit": i["unit"]})


def _h_outlook(db, t, demo, rep, q, cz):
    items = [i for i in rep["sections"]["guidance"]["items"] if i["kind"] == "commentary"]
    ql = q.lower()
    if "capacity" in ql or "expan" in ql:
        items = [i for i in items if i["metric"] == "capacity"] or items
    latest = sorted(items, key=lambda i: i.get("doc_date") or "")[-4:]
    if not latest:
        return [], None
    lines = ["Qualitative management commentary (no numeric target stated, so none is inferred):"]
    lines += [f"{i['doc_period']}: “{i['text']}” [{cz.doc(i['citation'])}]" for i in latest]
    return lines, None


def _h_growth(db, t, demo, rep, q, cz):
    tr = rep["sections"]["trajectory"]
    return [f"{h['label']} [{cz.fin(h['evidence'])}] ({h['direction']})" for h in tr["highlights"]], None


HANDLERS = {"business": _h_business, "margin": _h_margin, "cash": _h_cash, "debt": _h_debt, "risks": _h_risks, "guidance": _h_guidance,
            "quarters": _h_quarters, "outlook": _h_outlook, "calls_diff": _h_calls_diff, "growth": _h_growth}


def _relevant(question: str, text: str) -> bool:
    """Guard against weak lexical matches: at least 2 distinct content words (or all of them if fewer) must appear."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as SW
    terms = {w for w in re.findall(r"[a-z]{3,}", question.lower()) if w not in SW and w not in {"company", "tell", "give", "show"}}
    if not terms:
        return False
    body = retrieval.strip_boilerplate(text).lower()
    found = sum(1 for w in terms if w in body)
    return found >= min(2, len(terms)) and found / len(terms) >= 0.5


# ------------------------------------------------------------------ main entry
def answer(db: Session, ticker: str, question: str, history: Optional[list[dict]] = None) -> dict:
    ticker = ticker.upper()
    demo = is_demo(db)
    prev_intent = next((m.get("meta", {}).get("intent") for m in reversed(history or []) if m["role"] == "assistant" and m.get("meta", {}).get("intent")), None)
    intent = detect_intent(question, prev_intent)
    rep = ra.get_or_build(db, ticker)
    cz = Cites()
    lines, table = [], None
    if intent and rep.get("status") != "insufficient_data":
        try:
            lines, table = HANDLERS[intent](db, ticker, demo, rep, question, cz)
        except Exception as e:
            log.exception("handler %s failed: %s", intent, e)
            lines, table = [], None
    hits = [h for h in retrieval.search(db, ticker, question, k=3, is_demo=demo) if _relevant(question, h.text)]
    if not lines and hits:
        lines = ["The closest passages in the company's documents:"] + [f"“{ra._lead_text(h.text, 2) or re.sub(chr(10), ' ', retrieval.strip_boilerplate(h.text))[:240]}” [{cz.doc(h.citation())}]" for h in hits[:2]]
    if not lines:
        why = ("no documents or financials are indexed for this company in the current data mode" if rep.get("status") == "insufficient_data"
               else "none of the indexed documents or financial tables addresses this question")
        return {"answer": f"Insufficient evidence: {why}. I won't answer from general knowledge. Try a question about the company's reported financials, segments, guidance or risks, or add its annual report / transcripts.",
                "citations": [], "table": None, "generated_by": "deterministic", "verified": True, "intent": intent, "insufficient": True,
                "is_demo": demo, "suggestions": SUGGESTIONS[:3]}
    det = "\n".join(lines)
    out = {"answer": det, "citations": cz.items, "table": table, "generated_by": "deterministic (structured data + retrieved excerpts)", "verified": True,
           "intent": intent, "insufficient": False, "is_demo": demo}
    p = llm_mod.get_llm()
    if p.available() and cz.items:
        src_lines = []
        for c in cz.items:
            src_lines.append(f"[{c['n']}] " + (f"{c['label']}: periods {c['periods']} values {c['values']}" if c["kind"] == "financial" else f"{c['title']} p.{c['page']}: {c['excerpt']}"))
        src = "\n".join(src_lines) + "\n\nVERIFIED FACTS:\n" + det
        try:
            hist = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in (history or [])[-4:])
            txt = p.generate(f"Conversation so far:\n{hist}\n\nQuestion: {question}\n\nSOURCES:\n{src}\n\nAnswer in at most 120 words using ONLY the sources. Cite as [n]. "
                             "Use only numbers that appear in the sources. If the sources do not answer the question, say the evidence is insufficient. No investment advice.",
                             system="You are a careful equity-research assistant. You never use outside knowledge.", max_tokens=300)
            valid_refs = {c["n"] for c in cz.items}
            refs = {int(x) for x in re.findall(r"\[(\d+)\]", txt)}
            if txt and refs and refs <= valid_refs and _numbers_in(txt) <= (_numbers_in(src) | {str(i) for i in range(1, 10)}):
                out.update(answer=txt, generated_by=f"ollama:{p.model} (verified against sources)")
            else:
                out["generated_by"] = "deterministic (model answer rejected: unverifiable figures or citations)"
        except Exception as e:
            log.info("LLM answer failed: %s", e)
    return out
