"""Priority engine: every score is built from named, explainable components (no opaque number).

priority: critical >= 80, high >= 55, medium >= 30, else low.
Routine paperwork (unclassified + most compliance) is capped so it can never outrank a material event.
"""
from __future__ import annotations

import re
from typing import Optional

BASE = {
    "results": 64, "M&A": 60, "fund_raise": 52, "management_change": 50, "litigation": 55, "insider_trading": 30,
    "earnings_call": 34, "investor_meetings": 16, "credit_rating": 40, "dividend": 45, "bonus_split": 48,
    "capex": 52, "press_release": 30, "postal_ballot": 22, "agm_egm": 20, "pledging": 45, "unclassified": 8,
}
PRIORITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}

AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakh crore|crore|cr\b|lakh|million|mn\b|billion|bn\b)", re.I)
# thresholds in ₹ crore: (strong, notable) by company size
THRESH = {"large": (5000, 1000), "mid": (1000, 200), "small": (300, 50)}
SEVERE = r"fraud|forensic|insolvency|\bcirp\b|default|going concern|qualified opinion|search (and|&) seizure|raid|enforcement directorate|\bcbi\b|ban(ned)? from|debarr"
IMMEDIATE_EXIT = r"with immediate effect|resign(ed|ation)? .{0,40}(personal|other) (reasons|commitments)|abrupt"


def amount_in_crore(text: str) -> Optional[float]:
    best = None
    for m in AMOUNT.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        u = m.group(2).lower()
        v = v * 100000 if "lakh crore" in u else v / 100 if u == "lakh" else v / 10 if u in ("million", "mn") else v * 100 if u in ("billion", "bn") else v
        best = max(best or 0, v)
    return best


def score_announcement(*, category: str, headline: str, body: str = "", size_bucket: str = "large",
                       in_portfolio: bool = True, extracted: Optional[dict] = None) -> dict:
    text = f"{headline}\n{(body or '')[:3000]}"
    score = BASE.get(category, 8)
    reasons = [f"Base weight for ‘{category}’: {score}"]

    def add(points: int, why: str):
        nonlocal score
        score += points
        reasons.append(f"{'+' if points >= 0 else ''}{points} {why}")

    low_head = headline.lower()
    if category == "management_change":
        senior = re.search(r"\b(ceo|cfo|coo|md|managing director|chief (executive|financial|operating)|chairman|chairperson|whole[- ]time)\b", low_head)
        junior = re.search(r"company secretary|compliance officer|senior management|key managerial", low_head)
        if senior:
            add(28, "top-level role (CEO/CFO/MD/Chair) is changing")
        elif junior:
            add(-25, "company-secretary / compliance-level role – usually routine")
        elif re.search(r"independent director|non-?executive", low_head):
            add(-15, "board-level (non-executive) change")
        if re.search(IMMEDIATE_EXIT, text, re.I):
            add(15, "exit is abrupt / with immediate effect")
    elif category == "credit_rating":
        if re.search(r"downgrad|negative outlook|watch with negative", text, re.I):
            add(40, "rating downgrade / negative outlook raises borrowing-cost and refinancing risk")
        elif re.search(r"upgrad|positive outlook", text, re.I):
            add(22, "rating upgrade")
        elif re.search(r"reaffirm", text, re.I):
            add(-15, "rating reaffirmed – no change")
    elif category == "pledging":
        if re.search(r"creat|increase|additional|invocation|invoked", text, re.I):
            add(15, "pledge created/increased or invoked")
        elif re.search(r"releas|revok", text, re.I):
            add(-15, "pledge released (positive)")
    elif category == "litigation":
        if re.search(SEVERE, text, re.I):
            add(25, "severe terms (fraud / insolvency / default / enforcement)")
    elif category == "insider_trading":
        if re.search(r"\bsold|sale|dispos", low_head):
            add(8, "insider/promoter selling")
    elif category == "press_release":
        if re.search(r"clarification|rumou?r|news (item|report)|speculation", text, re.I):
            add(15, "company is responding to market speculation")
    elif category == "results":
        if re.search(r"intimation|schedule|prior intimation|date of board meeting", low_head) and not extracted:
            add(-30, "only a meeting intimation – results not out yet")

    # financial materiality from any rupee amounts mentioned
    amt = amount_in_crore(text)
    if amt and category not in ("unclassified", "agm_egm", "postal_ballot"):
        strong, notable = THRESH.get(size_bucket, THRESH["large"])
        if amt >= strong:
            add(15, f"large amount (₹{amt:,.0f} cr ≥ ₹{strong:,} cr for a {size_bucket}-cap)")
        elif amt >= notable:
            add(8, f"notable amount (₹{amt:,.0f} cr)")

    # results surprise: big YoY swings deserve attention
    if category == "results" and extracted and extracted.get("metrics"):
        pat = extracted["metrics"].get("pat", {}).get("yoy", {}).get("pct")
        rev = extracted["metrics"].get("revenue", {}).get("yoy", {}).get("pct")
        if pat is not None and (pat <= -15 or pat >= 25):
            add(12, f"PAT {pat:+.0f}% YoY is a large swing")
        elif rev is not None and abs(rev) >= 20:
            add(8, f"revenue {rev:+.0f}% YoY is a large swing")

    if category != "unclassified" and re.search(SEVERE, headline, re.I) and category != "litigation":
        add(12, "severe wording in headline")

    if in_portfolio:
        add(5, "company is in your portfolio")

    if category == "unclassified":
        score = min(score, 15)
        reasons.append("capped at 15: routine compliance paperwork")

    score = max(0, min(100, score))
    priority = "critical" if score >= 80 else "high" if score >= 55 else "medium" if score >= 30 else "low"
    return {"attention_score": score, "priority": priority, "reasons": reasons}


# ---------------------------------------------------------------- deterministic summaries
def _fmt(v: Optional[float]) -> str:
    return "n/a" if v is None else f"₹{v:,.0f} cr"


def _pct(g: dict) -> str:
    return f"{g['pct']:+.1f}%" if g and g.get("pct") is not None else "n.m."


def rule_summary(category: str, headline: str, company: str, extracted: Optional[dict]) -> dict:
    """What happened / why care / what to monitor – templated from structured fields only. Labelled 'rules'."""
    what, why, watch = headline, "", ""
    if category == "results" and extracted and extracted.get("metrics"):
        m = extracted["metrics"]
        rev, pat = m.get("revenue", {}), m.get("pat", {})
        if rev.get("current") is not None:
            what = (f"{company} reported revenue of {_fmt(rev['current'])} ({_pct(rev.get('yoy'))} YoY, {_pct(rev.get('qoq'))} QoQ)"
                    + (f" and PAT of {_fmt(pat.get('current'))} ({_pct(pat.get('yoy'))} YoY)." if pat.get("current") is not None else "."))
        why = "Results are the primary scheduled check on whether the business is delivering; YoY removes seasonality."
        watch = "Management commentary on the earnings call: margin outlook, guidance changes, and any one-offs inside PAT."
    elif category == "results":
        why = "Results are the primary scheduled check on business delivery."
        watch = "The numbers themselves once filed, and the earnings-call date."
    elif category == "management_change" and extracted and extracted.get("changes"):
        verbs = {"appointment": "appointed", "resignation": "resigned", "retirement": "retiring", "cessation": "ceased"}
        parts = []
        for c in extracted["changes"][:2]:
            role = c.get("designation") or "a senior role"
            eff = f" (effective {c['effective_date']})" if c.get("effective_date") else ""
            parts.append(f"{c['person']} {verbs.get(c['event'], c['event'])} as {role}{eff}")
        what = "; ".join(parts) + "."
        why = "Leadership changes in finance/operations roles can signal strategy shifts or governance issues; continuity of the succession matters."
        watch = "Whether a transition plan is disclosed, the stated reason for the exit, and any change in guidance on the next call."
    elif category == "management_change":
        why = "Leadership changes can signal strategy shifts or governance issues."
        watch = "Successor details and the stated reason for the change."
    else:
        why, watch = {
            "M&A": ("Changes the size, mix or risk of the business; price paid vs. size matters.", "Deal value, funding (debt vs. cash), regulatory approvals and expected closing."),
            "fund_raise": ("Raising capital dilutes owners or adds debt; the use of proceeds shows intent.", "Pricing vs. market price, size relative to market cap, and the stated use of funds."),
            "litigation": ("Orders and penalties can carry financial, reputational or licence risk.", "Quantum of the claim, appeal route, and whether a provision is disclosed."),
            "insider_trading": ("Promoter/insider trades can hint at conviction but are often routine or tax-driven.", "Size relative to total promoter holding and repeat activity."),
            "earnings_call": ("Calls are where guidance and tone are set.", "Transcript once published; compare guidance to the previous call."),
            "investor_meetings": ("Routine outreach; rarely changes the thesis.", "Nothing specific – informational."),
            "credit_rating": ("Ratings drive borrowing costs; changes are a credit-quality signal.", "Rating rationale, outlook, and leverage trend."),
            "dividend": ("Cash returned to shareholders; signals confidence in cash generation.", "Payout vs. earnings and the record date."),
            "bonus_split": ("Changes share count/price but not value – can improve liquidity and retail access.", "Record date and ratio."),
            "capex": ("Capacity spend commits cash today for growth later.", "Funding source, commissioning timeline, expected returns."),
            "press_release": ("Order wins, launches and clarifications can move sentiment.", "Order size relative to revenue and delivery timeline."),
            "postal_ballot": ("Shareholder approval step for specific resolutions.", "The resolutions being voted and the result."),
            "agm_egm": ("Governance event; resolutions may include appointments and related-party items.", "Agenda items and voting outcome."),
            "pledging": ("Pledged promoter shares are a leverage/risk signal.", "Total pledged % of promoter holding and any invocation."),
            "unclassified": ("Routine filing; not expected to move the stock.", "Nothing – filed under Routine updates."),
        }.get(category, ("", ""))
    return {"what": what, "why": why, "watch": watch, "by": "rules"}
