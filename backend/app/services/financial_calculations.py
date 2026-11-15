"""Deterministic financial calculations. No LLM is ever used for arithmetic.

Conventions
-----------
* Money is in INR crore unless a unit is stated.
* Every function returns None (never 0 or NaN) when an input is missing or the result is not meaningful,
  so the UI can show "unavailable" instead of a made-up number.
* `growth()` returns a dict so that the *reason* for an unavailable / non-meaningful figure travels with it.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

Number = Optional[float]

METHODOLOGY = {
    "growth": "((Current - Previous) / |Previous|) x 100. Not meaningful (n.m.) when Previous <= 0.",
    "ebitda_margin": "EBITDA / Revenue x 100",
    "pat_margin": "PAT / Revenue x 100",
    "debt_to_equity": "Total borrowings / Shareholders' equity (net worth). Not computed for banks/NBFCs.",
    "roe": "PAT / average shareholders' equity x 100 (closing equity if prior year unavailable)",
    "roce": "EBIT / average capital employed x 100, EBIT = PBT + finance costs, capital employed = equity + borrowings",
    "cfo_to_pat": "Cash flow from operations / PAT (ratio). Multi-year view uses cumulative sums.",
    "fcf": "Cash flow from operations - Capital expenditure",
    "volume_deviation": "Latest volume / mean volume of the previous 20 sessions (latest session excluded)",
}


def _ok(*vals: Number) -> bool:
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in vals)


def growth(current: Number, previous: Number) -> dict:
    """Percentage growth with an explanation when it cannot be computed."""
    if not _ok(current, previous):
        return {"pct": None, "note": "unavailable (missing input)"}
    if previous == 0:
        return {"pct": None, "note": "n.m. (previous period is zero)"}
    if previous < 0:
        if current > 0:
            return {"pct": None, "note": "n.m. (turnaround from a loss)"}
        return {"pct": None, "note": "n.m. (negative base)"}
    return {"pct": round((current - previous) / previous * 100, 2), "note": None}


def pct_change(current: Number, previous: Number) -> Number:
    return growth(current, previous)["pct"]


def qoq(current: Number, previous_quarter: Number) -> dict:
    return growth(current, previous_quarter)


def yoy(current: Number, same_quarter_last_year: Number) -> dict:
    return growth(current, same_quarter_last_year)


def margin(numerator: Number, revenue: Number) -> Number:
    if not _ok(numerator, revenue) or revenue <= 0:
        return None
    return round(numerator / revenue * 100, 2)


def ebitda_margin(ebitda: Number, revenue: Number) -> Number:
    return margin(ebitda, revenue)


def pat_margin(pat: Number, revenue: Number) -> Number:
    return margin(pat, revenue)


def debt_to_equity(debt: Number, equity: Number) -> Number:
    if not _ok(debt, equity) or equity <= 0:
        return None
    return round(debt / equity, 2)


def roe(pat: Number, equity: Number, prev_equity: Number = None) -> Number:
    if not _ok(pat, equity):
        return None
    base = (equity + prev_equity) / 2 if _ok(prev_equity) else equity
    if base <= 0:
        return None
    return round(pat / base * 100, 2)


def roce(pbt: Number, interest: Number, equity: Number, debt: Number,
         prev_equity: Number = None, prev_debt: Number = None) -> Number:
    if not _ok(pbt, interest, equity, debt):
        return None
    ebit = pbt + interest
    ce = equity + debt
    if _ok(prev_equity, prev_debt):
        ce = (ce + prev_equity + prev_debt) / 2
    if ce <= 0:
        return None
    return round(ebit / ce * 100, 2)


def cfo_to_pat(cfo: Number, pat: Number) -> Number:
    if not _ok(cfo, pat) or pat <= 0:
        return None
    return round(cfo / pat, 2)


def free_cash_flow(cfo: Number, capex: Number) -> Number:
    """FCF = CFO - Capex. `capex` is taken as a positive outflow."""
    if not _ok(cfo, capex):
        return None
    return round(cfo - abs(capex), 2)


def cagr(first: Number, last: Number, years: int) -> Number:
    if not _ok(first, last) or years <= 0 or first <= 0 or last <= 0:
        return None
    return round(((last / first) ** (1 / years) - 1) * 100, 2)


def volume_deviation(latest_volume: Number, prior_volumes: Sequence[float], window: int = 20) -> dict:
    """Return the 20-day average (excluding the latest session) and the multiple of the latest volume."""
    vols = [v for v in prior_volumes if _ok(v) and v > 0][-window:]
    if not _ok(latest_volume) or len(vols) < max(5, window // 4):
        return {"avg": None, "ratio": None, "pct": None}
    avg = sum(vols) / len(vols)
    if avg <= 0:
        return {"avg": None, "ratio": None, "pct": None}
    ratio = latest_volume / avg
    return {"avg": round(avg, 2), "ratio": round(ratio, 2), "pct": round((ratio - 1) * 100, 1)}


def annualised_volatility(closes: Sequence[float], window: int = 30) -> Number:
    c = [x for x in closes if _ok(x) and x > 0][-(window + 1):]
    if len(c) < 10:
        return None
    rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 2)


def trend_label(first: Number, last: Number, years: int, grow_thr: float = 8.0, shrink_thr: float = -2.0) -> str:
    """Classify a multi-year series as growing / stagnant / deteriorating by CAGR."""
    c = cagr(first, last, years)
    if c is None:
        return "unclear"
    if c >= grow_thr:
        return "growing"
    if c <= shrink_thr:
        return "deteriorating"
    return "stagnant"


def convert_to_crore(value: Number, unit: str) -> Number:
    """Convert a reported figure to INR crore. 1 crore = 10 million = 100 lakh."""
    if not _ok(value):
        return None
    u = (unit or "crore").lower()
    if "lakh" in u and "crore" not in u:
        return value / 100
    if "million" in u or u in {"mn", "mm"}:
        return value / 10
    if "billion" in u or u == "bn":
        return value * 100
    if "thousand" in u:
        return value / 10000
    return value
