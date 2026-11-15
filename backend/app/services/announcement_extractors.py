"""Structured extraction from filing text: quarterly results and management changes.

Everything here is regex/table parsing - deterministic, auditable, and never invents a number. When a figure cannot
be found it is returned as None with a note.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from . import financial_calculations as fc

NUM_CELL = re.compile(r"^\(?-?₹?\s*[\d,]+(?:\.\d+)?\)?$")
NUM_ANY = re.compile(r"\(?-?[\d,]*\d(?:\.\d+)?\)?")
DATE_PAT = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
NIL = {"-", "–", "—", "nil", "na", "n.a.", "n/a"}

ALIASES = {
    "revenue": [r"revenue from operations", r"net sales", r"income from operations", r"total revenue from operations",
                r"gross revenue", r"total income"],
    "other_income": [r"other income"],
    "finance_cost": [r"finance costs?", r"interest expense", r"interest cost"],
    "depreciation": [r"depreciation", r"amorti[sz]ation"],
    "pbt": [r"profit(?:/\(loss\))?\s*(?:/\(loss\))?\s*before tax", r"profit before tax", r"\bpbt\b"],
    "pat": [r"profit(?:/\(loss\))?\s*(?:/\(loss\))? for the (?:period|year|quarter)", r"net profit(?:/\(loss\))?(?: for the (?:period|year|quarter))?",
            r"profit after tax", r"\bpat\b"],
    "ebitda": [r"\bebitda\b", r"operating profit"],
}
METRIC_ORDER = ["revenue", "ebitda", "pbt", "pat"]


def parse_number(tok: str) -> Optional[float]:
    t = tok.strip().lower().replace("₹", "").replace("rs.", "").strip()
    if t in NIL or not t:
        return None
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.strip("()-").replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _cells(line: str) -> list[str]:
    if "|" in line:
        return [c.strip() for c in line.split("|")]
    parts = re.split(r"\t| {2,}", line.strip())
    return [p.strip() for p in parts]


def _numbers_in_line(line: str) -> tuple[str, list[Optional[float]]]:
    """Return (label, numbers). Works for 'a | 1 | 2 | 3' and for 'label 1,234 1,100 900' style lines."""
    cells = _cells(line)
    if len(cells) >= 3 and sum(bool(NUM_CELL.match(c) or c.lower() in NIL) for c in cells[1:]) >= 2:
        return cells[0], [parse_number(c) for c in cells[1:] if NUM_CELL.match(c) or c.lower() in NIL]
    m = re.match(r"^(.*?[A-Za-z\)])\s+((?:\(?-?[\d,]*\d(?:\.\d+)?\)?|[-–—])(?:\s+(?:\(?-?[\d,]*\d(?:\.\d+)?\)?|[-–—]))+)\s*$", line.strip())
    if m:
        nums = [parse_number(x) for x in m.group(2).split()]
        return m.group(1), nums
    return line.strip(), []


def detect_unit(text: str) -> str:
    low = text[:3000].lower()
    if re.search(r"lakh", low) and not re.search(r"crore", low):
        return "lakh"
    if re.search(r"in (rs\.?|₹|inr)?\s*million|₹\s*million|\bmn\b", low):
        return "million"
    if re.search(r"billion|\bbn\b", low):
        return "billion"
    if "crore" in low or " cr" in low:
        return "crore"
    return "crore (assumed)"


def quarter_label(d: date) -> str:
    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[d.month]
    fy = d.year + 1 if d.month >= 4 else d.year
    return f"Q{q} FY{str(fy)[-2:]}"


def _header_dates(text: str) -> list[date]:
    out = []
    for line in text.splitlines()[:40]:
        if re.search(r"quarter|ended|particulars", line, re.I):
            for dd, mm, yy in DATE_PAT.findall(line):
                try:
                    out.append(date(int(yy), int(mm), int(dd)))
                except ValueError:
                    pass
            if len(out) >= 3:
                break
    return out[:3]


def _consolidated_slice(text: str) -> tuple[str, str]:
    low = text.lower()
    ci = low.find("consolidated")
    si = low.find("standalone")
    if ci == -1 and si == -1:
        return text, "unspecified"
    if ci != -1 and (si == -1 or ci <= si or True):
        start = ci
        nxt = low.find("standalone", start + 12)
        return (text[start:nxt] if nxt != -1 else text[start:]), "consolidated"
    return text, "standalone"


def _pick(lines: list[tuple[str, list]], patterns: list[str], exclude: str = "") -> Optional[list]:
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for label, nums in lines:
            if len([n for n in nums if n is not None]) >= 1 and rx.search(label) and not (exclude and re.search(exclude, label, re.I)):
                return nums
    return None


def extract_results(text: str) -> Optional[dict]:
    """Extract Revenue / EBITDA / PBT / PAT for current quarter, previous quarter and same quarter last year."""
    if not text or len(text) < 40:
        return None
    section, basis = _consolidated_slice(text)
    unit = detect_unit(text)
    lines = []
    pending_label = None
    raw_lines = [l for l in section.splitlines() if l.strip()]
    for i, line in enumerate(raw_lines):
        label, nums = _numbers_in_line(line)
        if len(nums) >= 3:
            lines.append((label, nums))
        elif not nums and len(label) < 90:
            # PDF layouts often put label and numbers on separate lines
            following = []
            for nxt in raw_lines[i + 1:i + 4]:
                if NUM_CELL.match(nxt.strip()) or nxt.strip().lower() in NIL:
                    following.append(parse_number(nxt.strip()))
                else:
                    break
            if len(following) >= 3:
                lines.append((label, following))
    if not lines:
        return None

    found = {}
    for key in ["revenue", "other_income", "finance_cost", "depreciation", "pbt", "pat", "ebitda"]:
        pats = ALIASES[key]
        exclude = r"before (exceptional|tax)|attributable|per share|margin" if key == "pat" else (r"exceptional" if key == "pbt" else "")
        if key == "pbt":
            nums = _pick(lines, [r"profit(?:/\(loss\))? before tax$|profit before tax\b"], r"exceptional")
            nums = nums or _pick(lines, pats, "")
        else:
            nums = _pick(lines, pats, exclude)
        if nums:
            found[key] = nums[:3] + [None] * (3 - len(nums[:3]))

    if not found:
        return None
    dates = _header_dates(section) or _header_dates(text)
    notes = []
    verified = False
    periods = ["Current quarter", "Previous quarter", "Same quarter last year"]
    if len(dates) == 3:
        cur, prev, ya = dates
        gap_prev = (cur - prev).days
        gap_ya = (cur - ya).days
        if 70 <= gap_prev <= 110 and 350 <= gap_ya <= 380:
            verified = True
            periods = [quarter_label(cur), quarter_label(prev), quarter_label(ya)]
        else:
            notes.append("Column dates do not follow the standard (current, previous quarter, year-ago) order – "
                         "QoQ/YoY withheld to avoid comparing the wrong periods.")
            return {"basis": basis, "unit": unit, "column_order_verified": False, "periods": [d.isoformat() for d in dates],
                    "metrics": {}, "notes": notes}
    else:
        notes.append("Column headers not found; assumed the standard SEBI order (current, previous quarter, year-ago).")

    if "assumed" in unit:
        notes.append("Reporting unit not stated in the text; assumed ₹ crore.")

    def conv(v):
        return fc.convert_to_crore(v, unit)

    metrics = {}
    for key in METRIC_ORDER:
        derived = False
        vals = found.get(key)
        if key == "ebitda" and (not vals):
            comps = [found.get("pbt"), found.get("finance_cost"), found.get("depreciation"), found.get("other_income")]
            if all(comps):
                vals = []
                for i in range(3):
                    pbt, fin, dep, oi = (c[i] for c in comps)
                    vals.append(None if None in (pbt, fin, dep, oi) else pbt + fin + dep - oi)
                derived = True
                notes.append("EBITDA derived as PBT + finance costs + depreciation − other income (not reported directly).")
        if not vals:
            metrics[key] = {"current": None, "previous": None, "year_ago": None, "qoq": {"pct": None, "note": "not found in filing"},
                            "yoy": {"pct": None, "note": "not found in filing"}, "derived": False}
            continue
        c, p, y = (conv(v) for v in vals)
        metrics[key] = {"current": c, "previous": p, "year_ago": y, "qoq": fc.qoq(c, p), "yoy": fc.yoy(c, y), "derived": derived}
    return {"basis": basis, "unit": "INR crore", "reported_unit": unit, "column_order_verified": verified,
            "periods": periods, "metrics": metrics, "notes": notes}


# ---------------------------------------------------------------- management change
TITLE = r"(?:Mr|Ms|Mrs|Dr|Shri|Smt|Prof)\.?"
NAME = rf"{TITLE}\s+([A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){{0,3}})"
ROLE = (r"(Chief (?:Executive|Financial|Operating|Technology|Information|Risk|Business|Compliance|Human Resources?) Officer|CEO|CFO|COO|CTO|CIO|"
        r"Managing Director(?: (?:&|and) (?:CEO|Chief Executive Officer))?|Whole[- ]Time Director|Independent Director|"
        r"Non-Executive(?: Independent)? Director|Executive Director|Chairman|Chairperson|Company Secretary(?: (?:and|&) Compliance Officer)?|"
        r"Compliance Officer|Senior Management Personnel|Key Managerial Personnel|Director)")
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
EVENT_PATS = [
    ("resignation", r"resign|step(?:s|ping)? down|tendered"),
    ("retirement", r"retire|superannuat"),
    ("cessation", r"cease|cessation|demise|relieved"),
    ("appointment", r"appoint|induct|elevat|designat"),
]


def _parse_date(s: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})[,.\s]+(\d{4})", s)
    if m and m.group(2).lower()[:3] in {k[:3] for k in MONTHS}:
        mon = next(v for k, v in MONTHS.items() if k[:3] == m.group(2).lower()[:3])
        try:
            return date(int(m.group(3)), mon, int(m.group(1))).isoformat()
        except ValueError:
            return None
    m = DATE_PAT.search(s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def _effective_date(window: str, whole: str = "") -> Optional[str]:
    rx = r"(?:w\.e\.f\.?|with effect from|effective(?: from)?|from the close of business(?: hours)?(?: on)?|close of business(?: hours)? on|as of|on)\s+([^;]{6,70})"
    for src in (window, whole):
        for m in re.finditer(rx, src, re.I):
            d = _parse_date(m.group(1))
            if d:
                return d
    return None


def _event_before(text: str, name_start: int) -> Optional[str]:
    """Event keyword nearest *before* the name, e.g. 'resignation of Ms. X' / 'appointment of Mr. Y'."""
    window = text[max(0, name_start - 80):name_start]
    best, best_pos = None, -1
    for ev, pat in EVENT_PATS:
        for m in re.finditer(pat, window, re.I):
            if m.start() > best_pos:
                best, best_pos = ev, m.start()
    return best


def _brief_profile(text: str, person: str) -> Optional[str]:
    m = re.search(r"brief (?:profile|resume|background)[^:\n]*[:\-]\s*(.{40,900}?)(?:\n\s*\n|\n\s*\d+[.)]|disclosure of relationship|$)", text, re.I | re.S)
    if m:
        txt = re.sub(r"\s+", " ", m.group(1)).strip()
        return re.sub(r"\b(Mr|Ms|Mrs|Dr|Prof|Smt)\b(?!\.)", r"\1.", txt)
    return None


def extract_management_change(headline: str, body: str) -> Optional[dict]:
    text = f"{headline}. {body or ''}"
    text = re.sub(r"\b(Mr|Ms|Mrs|Dr|Prof|Smt)\.", r"\1", text)  # keep 'Mr. X' from being split as a sentence end
    prof = re.search(r"brief (?:profile|resume|background)", text, re.I)
    main_text = text[:prof.start()] if prof else text  # events are read from the disclosure, never from the profile prose
    changes = []
    sentences = re.split(r"(?<=[.;])\s+|\n+", main_text)
    seen: dict = {}
    for sent in sentences:
        names = list(re.finditer(NAME, sent))
        for i, nm in enumerate(names):
            ev = _event_before(sent, nm.start()) or next((n for n, pat in EVENT_PATS if re.search(pat, sent, re.I)), None)
            if not ev:
                continue
            person = nm.group(1).strip()
            seg_end = names[i + 1].start() if i + 1 < len(names) else len(sent)
            after = sent[nm.end():seg_end]            # text describing *this* person only
            role_m = re.search(ROLE, after) or re.search(ROLE, sent)
            role = role_m.group(1) if role_m else None
            key = (person, role)
            prev = None
            pm = re.search(rf"{re.escape(person.split()[-1])}[^.]{{0,40}}(?:is )?(?:currently|presently)\s+(?:serving |working )?(?:as\s+)?(?:the\s+)?([A-Z][A-Za-z&,\- ]{{4,70}}?)(?:\s+(?:at|of|in|with)\b|[.;,]|$)", text)
            pm = pm or re.search(r"(?:currently|presently)\s+(?:serving |working )?(?:as\s+)?(?:the\s+)?([A-Z][A-Za-z&,\- ]{4,70}?)(?:\s+(?:at|of|in|with)\b|[.;,]|$)", text)
            if pm and ev == "appointment":
                prev = pm.group(1).strip()
            profile = _brief_profile(text, person) if ev == "appointment" else None
            rec = {
                "person": person, "event": ev, "designation": role, "previous_designation": prev,
                "effective_date": _effective_date(after, sent),
                "brief_profile": profile,
                "profile_source": "Company filing (brief profile disclosed under SEBI LODR Reg. 30)" if profile else None,
            }
            if key in seen:  # same person/role seen in headline and body: merge, never drop information
                cur = seen[key]
                for f, v in rec.items():
                    if cur.get(f) is None and v is not None:
                        cur[f] = v
                if cur["event"] == "cessation" and ev != "cessation":
                    cur["event"] = ev
                continue
            seen[key] = rec
            changes.append(rec)
    if not changes:
        return None
    senior = bool(re.search(r"\b(ceo|cfo|coo|md|managing director|chief executive|chief financial|chief operating|chairman|chairperson|whole[- ]time)\b", text, re.I))
    return {"changes": changes, "senior_role": senior,
            "notes": ["Profile text, where shown, is quoted from the filing itself. No external biography was fetched."]}
