from app.services.announcement_extractors import extract_results, extract_management_change, parse_number, detect_unit
from app.services.prioritisation import score_announcement, amount_in_crore, rule_summary

RESULTS = """Acme Ltd
Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026
(Rs. in crore)
Particulars | Quarter ended 30.09.2026 | Quarter ended 30.06.2026 | Quarter ended 30.09.2025 | Half year ended 30.09.2026
Revenue from operations | 1,23,456 | 1,20,000 | 1,10,000 | -
Other income | 500 | 480 | 450 | -
Finance costs | 1,000 | 1,000 | 900 | -
Depreciation and amortisation expense | 2,000 | 1,900 | 1,800 | -
Profit before tax | 15,000 | 14,000 | 12,000 | -
Profit for the period | 11,000 | (1,200) | 9,000 | -
"""


def test_parse_number_indian_format_and_negatives():
    assert parse_number("1,23,456.78") == 123456.78
    assert parse_number("(1,200)") == -1200
    assert parse_number("-") is None
    assert parse_number("abc") is None


def test_results_extraction_values_and_growth():
    r = extract_results(RESULTS)
    assert r["column_order_verified"] is True
    assert r["periods"] == ["Q2 FY27", "Q1 FY27", "Q2 FY26"]
    rev = r["metrics"]["revenue"]
    assert (rev["current"], rev["previous"], rev["year_ago"]) == (123456, 120000, 110000)
    assert rev["qoq"]["pct"] == 2.88 and rev["yoy"]["pct"] == 12.23
    # EBITDA is not in the filing -> derived = PBT + finance + dep - other income
    e = r["metrics"]["ebitda"]
    assert e["derived"] is True and e["current"] == 15000 + 1000 + 2000 - 500
    # negative previous PAT: growth must be n.m., never a fake percentage
    pat = r["metrics"]["pat"]
    assert pat["qoq"]["pct"] is None and "n.m." in pat["qoq"]["note"]


def test_results_wrong_column_order_is_refused():
    bad = RESULTS.replace("30.06.2026", "30.09.2026")
    r = extract_results(bad)
    assert r["column_order_verified"] is False and r["metrics"] == {}


def test_results_missing_numbers_returns_none():
    assert extract_results("Outcome of board meeting. Results will be published on the website.") is None


def test_unit_detection_and_conversion():
    assert detect_unit("(Rs. in lakhs)") == "lakh"
    r = extract_results(RESULTS.replace("Rs. in crore", "Rs. in million"))
    assert r["metrics"]["revenue"]["current"] == 12345.6  # million -> crore


MGMT = ("Board approved the appointment of Mr. Karthik Venkatesan as Chief Financial Officer with effect from 1 December 2026, consequent to the "
        "resignation of Ms. Meera Joshi as Chief Financial Officer with effect from the close of business hours on 30 November 2026.\n\n"
        "Mr. Karthik Venkatesan is currently serving as Executive Vice President - Finance at Orion Capital Ltd.\n\n"
        "Brief profile: Mr. Karthik Venkatesan is a Chartered Accountant with over 22 years of experience in treasury and reporting.\n\n"
        "Disclosure of relationships: none")


def test_management_change_two_people_one_sentence():
    r = extract_management_change("Appointment of CFO and resignation of CFO", MGMT)
    by = {c["person"]: c for c in r["changes"]}
    assert by["Karthik Venkatesan"]["event"] == "appointment" and by["Karthik Venkatesan"]["effective_date"] == "2026-12-01"
    assert by["Karthik Venkatesan"]["previous_designation"] == "Executive Vice President - Finance"
    assert "Chartered Accountant" in by["Karthik Venkatesan"]["brief_profile"]
    assert by["Meera Joshi"]["event"] == "resignation" and by["Meera Joshi"]["effective_date"] == "2026-11-30"
    assert by["Meera Joshi"]["brief_profile"] is None          # never invent a bio
    assert r["senior_role"] is True


def test_management_change_none_when_no_person():
    assert extract_management_change("Change in directorate", "The board changed.") is None


def test_amount_parsing():
    assert amount_in_crore("capex of Rs. 3,200 crore") == 3200
    assert amount_in_crore("Rs. 1 lakh crore") == 100000
    assert amount_in_crore("no amount") is None


def test_priority_ordering_and_explainability():
    hi = score_announcement(category="management_change", headline="Resignation of Chief Financial Officer with immediate effect")
    lo = score_announcement(category="management_change", headline="Resignation of Company Secretary and Compliance Officer")
    routine = score_announcement(category="unclassified", headline="Allotment under ESOP")
    assert hi["priority"] == "critical" and lo["priority"] in ("medium", "low") and routine["priority"] == "low"
    assert routine["attention_score"] <= 15
    assert hi["attention_score"] > lo["attention_score"] > routine["attention_score"]
    assert all(isinstance(r, str) and r for r in hi["reasons"]) and len(hi["reasons"]) >= 3


def test_big_results_swing_escalates():
    ext = {"metrics": {"pat": {"yoy": {"pct": -33}}, "revenue": {"yoy": {"pct": 2}}}}
    calm = score_announcement(category="results", headline="Financial results", extracted={"metrics": {"pat": {"yoy": {"pct": 3}}}})
    big = score_announcement(category="results", headline="Financial results", extracted=ext)
    assert big["attention_score"] > calm["attention_score"] and big["priority"] == "critical" and calm["priority"] == "high"


def test_rating_downgrade_beats_reaffirmation():
    d = score_announcement(category="credit_rating", headline="ICRA downgrades rating")
    r = score_announcement(category="credit_rating", headline="CRISIL reaffirms AAA")
    assert d["attention_score"] >= 55 > r["attention_score"]


def test_amount_scales_with_company_size():
    big = score_announcement(category="capex", headline="Board approves capex of Rs. 1,200 crore", size_bucket="small")
    small = score_announcement(category="capex", headline="Board approves capex of Rs. 1,200 crore", size_bucket="large")
    assert big["attention_score"] > small["attention_score"]


def test_summary_never_invents_when_extraction_missing():
    s = rule_summary("results", "Financial results", "Acme", None)
    assert "₹" not in s["what"] and s["by"] == "rules"
