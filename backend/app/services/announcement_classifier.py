"""Hybrid announcement classifier: weighted rules + context suppression -> optional local-LLM refinement.

Design notes
------------
* Pure keyword matching misclassifies a lot of exchange filings ("acquisition of shares by promoter" is NOT M&A,
  "allotment of shares under ESOP" is NOT a fund raise). Each rule therefore has *suppressors*: context patterns
  that void the rule when present in the headline.
* Headline matches count fully; body matches count 0.4x (bodies are noisy boilerplate).
* Output is always structured: {category, confidence, classifier, reasons[]}. Low evidence -> `unclassified`.
* If confidence < LLM_THRESHOLD and a local LLM is running, the LLM is asked for JSON and its answer is
  validated against the taxonomy before use. If it is unavailable or returns junk we keep the rules result.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from . import llm as llm_mod

log = logging.getLogger(__name__)

CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call",
    "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
    "agm_egm", "pledging", "unclassified",
]

LLM_THRESHOLD = 0.72
BODY_WEIGHT = 0.4


@dataclass
class Rule:
    category: str
    patterns: list[tuple[str, float]]
    suppress: list[str] = field(default_factory=list)  # if any matches in HEADLINE, rule is voided

    def __post_init__(self):
        self._pats = [(re.compile(p, re.I), w) for p, w in self.patterns]
        self._sup = [re.compile(s, re.I) for s in self.suppress]


ESOP = r"\besop\b|\besos\b|\besps\b|employee stock (option|purchase)|stock option scheme|sweat equity"
PROMOTER_TRADE = r"regulation\s*7\s*\(2\)|reg\.?\s*7\s*\(2\)|insider trading|\bpit\b regulations|promoter.{0,40}(acquir|purchas|sold|sale|dispos|buy)|(acquir|purchas|dispos).{0,40}by (the )?promoter|regulation\s*29\b|designated person"
AUDITOR = r"(secretarial|statutory|internal|cost) auditor|scrutini[sz]er"
TRADING_WINDOW = r"trading window"

RULES: list[Rule] = [
    Rule("insider_trading", [(PROMOTER_TRADE, 2.2), (r"disclosure under (regulation|reg)\s*(7|29)", 1.5)],
         suppress=[r"pledge|encumbr"]),
    Rule("pledging", [(r"\bpledg", 2.4), (r"encumbrance|invocation of pledge|release of pledge|regulation\s*31", 1.8)]),
    Rule("credit_rating", [(r"credit rating|rating (agency|action|rationale)|\bcrisil\b|\bicra\b|care ratings|india ratings|ind-?ra\b|fitch|moody|acuit[eé]|brickwork", 2.2),
                           (r"reaffirm|upgrad|downgrad|outlook (revised|changed)|assign(ed|s)? .{0,20}rating", 1.0)]),
    Rule("management_change", [
        (r"(appointment|resignation|cessation|retire|re-?appoint|relinquish|step(s|ping)? down|demise|superannuat|change in (directorate|management|key managerial|senior management))", 1.6),
        (r"\b(ceo|cfo|coo|cto|cio|md|chief (executive|financial|operating|technology|information|risk|business|compliance)|managing director|whole[- ]time director|company secretary|compliance officer|chairman|chairperson|independent director|non-?executive director|key managerial|senior management|kmp)\b", 1.4)],
        suppress=[AUDITOR, ESOP, r"appointment of (registrar|rta|scrutini)", r"allot"]),
    Rule("earnings_call", [(r"(earnings|conference|con|analyst|investor|results) call|concall|con-call|call transcript|transcript of|audio (recording|link)|webcast", 2.4)],
         suppress=[r"schedule of (analyst|institutional)"]),
    Rule("investor_meetings", [(r"analyst.{0,12}(meet|institutional)|investor (meet|conference|day)|institutional investor|one[- ]on[- ]one|group meeting|schedule of (analyst|investor)|roadshow|investor interaction|conference (organi[sz]ed|hosted) by", 2.4)]),
    Rule("results", [
        (r"financial results|unaudited|audited (standalone|consolidated|financial)|(quarter|half[- ]year|year|period) ended|results for the (quarter|year|period)|(q[1-4]|h[12]|fy)\s*\d{2}.{0,20}results|board meeting.{0,80}(results|financial)|outcome of board meeting.{0,120}results|results presentation|shareholder'?s? letter|newspaper.{0,40}results|publication of (financial )?results|earnings release|earnings presentation", 2.4)],
        suppress=[r"(earnings|conference|analyst|results) call"]),
    Rule("dividend", [(r"\bdividend\b|record date.{0,40}dividend|payout", 2.3)], suppress=[r"dividend distribution policy"]),
    Rule("bonus_split", [(r"bonus (issue|share|equity)|issue of bonus|stock split|sub-?division of (equity )?shares?|split of (equity )?shares?|face value.{0,30}(sub-?divi|split)", 2.5)]),
    Rule("fund_raise", [
        (r"rights issue|\bqip\b|qualified institutional placement|preferential (issue|allot)|buy[- ]?back|commercial paper|non[- ]convertible (debenture|bond)s?|\bncds?\b|(raising|raise|issue of|issuance of).{0,60}(bonds|debentures|notes)\b|\bat1\b|tier[- ]?(1|2|i|ii) (bonds|capital)|fund[- ]?rais|raising of (funds|capital)|raise (funds|capital)|\bfccb\b|\becb\b|external commercial borrowing|issue of (equity|debentures|bonds|warrants|convertible)|private placement|\bipo\b|\bfpo\b|\bofs\b|offer for sale", 2.3)],
        suppress=[ESOP, PROMOTER_TRADE, r"allotment of .{0,40}(esop|stock option)"]),
    Rule("M&A", [
        (r"acqui(re|sition|ring)|merger|amalgamat|scheme of arrangement|demerger|de-?merger|joint venture|\bjv\b|slump sale|wholly[- ]owned subsidiary|incorporation of|divest|share purchase agreement|\bspa\b|stake (sale|purchase)|(sale|purchase|investment) of .{0,30}(stake|equity|shares) in|business transfer|strategic investment|takeover|open offer", 2.0)],
        suppress=[PROMOTER_TRADE, ESOP, r"acquisition of (equity )?shares? by", r"regulation\s*(7|29)"]),
    Rule("capex", [(r"\bcapex\b|capital expenditure|new (plant|facility|factory|manufacturing|unit|refinery|line)|capacity (expansion|addition|enhancement)|greenfield|brownfield|set(ting)? up (of )?(a |an |the )?(new )?(plant|unit|facility|factory)|expansion of (plant|capacity|facility)|commission(ing)? of", 2.2)]),
    Rule("litigation", [
        (r"show[- ]cause|sebi.{0,40}order|order.{0,30}(passed|issued) by|adjudicat|penalt(y|ies)|\bfine[sd]?\b|demand (order|notice)|tax (demand|assessment|order)|\bgst\b.{0,30}(demand|order|notice)|\bnclt\b|\bnclat\b|insolvency|\bcirp\b|tribunal|writ petition|litigation|arbitration|\bcourt\b|regulatory action|warning letter|\bfda\b|\bcci\b|enforcement directorate|search (and|&) seizure|\bcbi\b|fraud|default", 2.3)],
        suppress=[r"outcome of (board|agm)", r"loss of share"]),
    Rule("press_release", [(r"press release|media release|clarification|news (item|report|article)|rumou?r|market speculation|order (win|received|worth)|bags? (an? )?order|receipt of (an? )?order|letter of (award|intent)|\bloa\b|\bloi\b|launch(es|ed)?\b|partnership|collaborat|\bmou\b|memorandum of understanding|awarded|wins?\b contract|product (launch|approval)|usfda approval|approval (received|from)", 1.9)],
         suppress=[r"order (passed|issued) by"]),
    Rule("postal_ballot", [(r"postal ballot|e-?voting results? of postal", 2.8)]),
    Rule("agm_egm", [(r"annual general meeting|\bagm\b|extra-?ordinary general meeting|\begm\b|book closure|record date.{0,30}(agm|meeting)|proceedings of (the )?(agm|egm)", 2.2)],
         suppress=[r"postal ballot"]),
    Rule("unclassified", [
        (ESOP, 2.6), (TRADING_WINDOW, 3.0), (AUDITOR, 2.2),
        (r"compliance certificate|regulation\s*74\s*\(5\)|certificate under|\besg\b|\bbrsr\b|sustainability report|secretarial compliance|annual secretarial|loss of share certificate|duplicate (share )?certificate|statement of investor complaints|regulation\s*13\s*\(3\)|reconciliation of share capital|regulation\s*40|regulation\s*24a|shareholding pattern|voting results|change in (rta|registrar)|updat(e|ion) (on|of) website|newspaper (advertisement|publication)|intimation of (closure|change in (address|name of rta))|disclosure.{0,20}(regulation 30|reg 30).{0,40}(general|updates)", 2.0)]),
]


@dataclass
class Classification:
    category: str
    confidence: float
    classifier: str = "rules"
    reasons: list[str] = field(default_factory=list)

    def as_dict(self):
        return {"category": self.category, "confidence": round(self.confidence, 2),
                "classifier": self.classifier, "reasons": self.reasons}


def _score_rule(rule: Rule, headline: str, body: str) -> tuple[float, list[str]]:
    if any(s.search(headline) for s in rule._sup):
        return 0.0, []
    score, why = 0.0, []
    for pat, w in rule._pats:
        m = pat.search(headline)
        if m:
            score += w
            why.append(f"headline matched “{m.group(0)[:40]}”")
        elif body and (mb := pat.search(body[:4000])):
            score += w * BODY_WEIGHT
            why.append(f"body matched “{mb.group(0)[:40]}”")
    return score, why


def classify_rules(headline: str, body: Optional[str] = None) -> Classification:
    headline = (headline or "").strip()
    body = body or ""
    scored = []
    for rule in RULES:
        s, why = _score_rule(rule, headline, body)
        if s > 0:
            scored.append((s, rule.category, why))
    if not scored:
        return Classification("unclassified", 0.3, "rules", ["no rule matched – defaulting to unclassified"])
    scored.sort(key=lambda x: -x[0])
    top_s, top_c, why = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if top_s < 0.9:
        return Classification("unclassified", 0.35, "rules",
                              [f"weak evidence for {top_c} (score {top_s:.1f}) – defaulting to unclassified"])
    margin_bonus = min(0.25, (top_s - second) * 0.12)
    conf = min(0.96, 0.5 + 0.09 * top_s + margin_bonus)
    reasons = why[:3]
    if second and top_s - second < 0.8:
        reasons.append(f"close call with {scored[1][1]}")
        conf = min(conf, 0.68)
    return Classification(top_c, conf, "rules", reasons)


LLM_SYSTEM = (
    "You classify Indian stock-exchange corporate announcements. Reply with ONLY compact JSON: "
    '{"category": <one of the allowed>, "confidence": <0-1>, "reason": <max 15 words>}.'
)


def classify_llm(headline: str, body: Optional[str], hint: Classification) -> Optional[Classification]:
    provider = llm_mod.get_llm()
    if not provider.available():
        return None
    prompt = (
        f"Allowed categories: {', '.join(CATEGORIES)}.\n"
        "Definitions: results=quarterly/annual results & board meetings approving them; M&A=acquisition/merger/JV/stake sale; "
        "fund_raise=rights/QIP/preferential/buyback/NCD/CP; management_change=CEO/CFO/MD/director joining/leaving; "
        "litigation=lawsuits/regulatory orders/fines/insolvency; insider_trading=promoter/insider personal share trades; "
        "earnings_call=call notice/transcript; investor_meetings=analyst/investor meets; credit_rating=rating actions; "
        "dividend; bonus_split; capex=new plant/capacity; press_release=orders, launches, clarifications; "
        "postal_ballot; agm_egm; pledging=promoter share pledge; unclassified=routine compliance (ESOP allotments, certificates, ESG, auditor appointments).\n"
        f"Rule-based guess: {hint.category} ({hint.confidence:.2f}).\n"
        f"HEADLINE: {headline}\nBODY: {(body or '')[:1200]}"
    )
    try:
        raw = provider.generate(prompt, system=LLM_SYSTEM, json_mode=True, max_tokens=120)
        data = json.loads(raw) if isinstance(raw, str) else raw
        cat = data.get("category")
        conf = float(data.get("confidence", 0.6))
        if cat not in CATEGORIES:
            return None
        return Classification(cat, max(0.0, min(conf, 0.92)), "llm", [f"LLM: {str(data.get('reason', ''))[:100]}"])
    except Exception as e:  # LLM output is untrusted – fall back silently
        log.info("LLM classification failed (%s); keeping rules result", e)
        return None


def classify(headline: str, body: Optional[str] = None, use_llm: bool = True) -> Classification:
    base = classify_rules(headline, body)
    if use_llm and base.confidence < LLM_THRESHOLD:
        refined = classify_llm(headline, body, base)
        if refined:
            # Agreement raises confidence; disagreement defers to the LLM only if it is more confident.
            if refined.category == base.category:
                return Classification(base.category, min(0.95, base.confidence + 0.15), "rules+llm",
                                      base.reasons + refined.reasons)
            if refined.confidence >= base.confidence:
                refined.reasons.append(f"overrode rules guess ‘{base.category}’")
                return refined
    return base
