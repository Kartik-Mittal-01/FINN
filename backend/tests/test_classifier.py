import pytest
from app.services.announcement_classifier import classify, classify_rules


CASES = [
    ("Outcome of Board Meeting - Unaudited Standalone and Consolidated Financial Results for the quarter ended 30th September 2026", "results"),
    ("Intimation of Board Meeting to consider unaudited financial results for the quarter and half year ended September 30, 2026", "results"),
    ("Newspaper publication of financial results", "results"),
    ("Transcript of Earnings Call for Q2 FY27", "earnings_call"),
    ("Intimation of Earnings Call to discuss Q2 results", "earnings_call"),
    ("Schedule of Analyst / Institutional Investor Meetings", "investor_meetings"),
    ("Appointment of Mr. Arvind Rao as Chief Financial Officer and resignation of Ms. Neha Kulkarni", "management_change"),
    ("Cessation of Mr. Rao as Managing Director", "management_change"),
    ("Resignation of Company Secretary and Compliance Officer", "management_change"),
    ("Disclosure under Regulation 7(2) of SEBI (PIT) Regulations – acquisition of shares by promoter", "insider_trading"),
    ("Allotment of equity shares pursuant to ESOP", "unclassified"),
    ("Closure of Trading Window", "unclassified"),
    ("Appointment of Secretarial Auditor", "unclassified"),
    ("CRISIL reaffirms AAA rating on the company's bank facilities", "credit_rating"),
    ("ICRA downgrades long-term rating to AA", "credit_rating"),
    ("Board recommends final dividend of Rs. 8 per share; record date fixed", "dividend"),
    ("Issue of bonus shares in the ratio 1:1", "bonus_split"),
    ("Approval of sub-division of equity shares (stock split)", "bonus_split"),
    ("Board approves capex of Rs. 2,500 crore for new manufacturing plant", "capex"),
    ("Acquisition of 51% stake in Orion Specialty Chemicals Pvt Ltd", "M&A"),
    ("Scheme of Arrangement – merger of wholly-owned subsidiary", "M&A"),
    ("Launch of Qualified Institutional Placement (QIP)", "fund_raise"),
    ("Issue of Non-Convertible Debentures aggregating to Rs. 1,000 crore", "fund_raise"),
    ("Issue of Basel III compliant Non-Convertible Bonds aggregating to Rs. 10,000 crore", "fund_raise"),
    ("Show cause notice received from SEBI", "litigation"),
    ("GST demand order received from Commissioner", "litigation"),
    ("Creation of pledge on promoter shares", "pledging"),
    ("Notice of Postal Ballot", "postal_ballot"),
    ("Notice of 45th Annual General Meeting", "agm_egm"),
    ("Clarification on news item appearing in media", "press_release"),
    ("Bags order worth Rs. 800 crore", "press_release"),
]


@pytest.mark.parametrize("headline,expected", CASES)
def test_rules(headline, expected):
    assert classify_rules(headline).category == expected, classify_rules(headline)


def test_context_beats_keywords():
    # 'acquisition' present but it is a promoter share purchase -> insider_trading, not M&A
    assert classify_rules("Acquisition of equity shares by promoter under Regulation 29").category == "insider_trading"
    # 'allotment' of ESOP shares is not a fund raise
    assert classify_rules("Allotment of 25,000 equity shares under Employee Stock Option Scheme").category == "unclassified"


def test_unknown_defaults_to_unclassified_with_low_confidence():
    c = classify_rules("Miscellaneous communication")
    assert c.category == "unclassified" and c.confidence < 0.5


def test_structured_output_and_confidence_bounds():
    c = classify("Board approves capex of Rs. 2,500 crore for new manufacturing plant", use_llm=False).as_dict()
    assert set(c) == {"category", "confidence", "classifier", "reasons"}
    assert 0 <= c["confidence"] <= 1 and c["reasons"]


def test_body_only_evidence_is_weaker_than_headline():
    h = classify_rules("Outcome of Board Meeting", "The board approved unaudited financial results for the quarter ended 30 September 2026")
    assert h.category == "results"
