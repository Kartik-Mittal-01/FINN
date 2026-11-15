"""Pull-side tests: PDF -> chunks -> retrieval -> guidance -> research report -> copilot, on a company FINN has never seen."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database import SessionLocal, init_db
from app.models import Document, Chunk
from app.services import company_discovery as cd, copilot, document_ingestion as di, guidance as gd, llm as llm_mod, pdf_extraction, research_agent as ra, retrieval
from app.services.state import set_setting
from app.config import settings

SCREENER_HTML = """
<html><body><h1 class="h2 shrink-text">Zenith Widgets Ltd</h1>
<section id="quarters"><table class="data-table"><thead><tr><th class="text"></th><th>Dec 2025</th><th>Mar 2026</th><th>Jun 2026</th><th>Sep 2026</th></tr></thead><tbody>
<tr><td class="text"><button>Sales&nbsp;<span>+</span></button></td><td>2,400</td><td>2,500</td><td>2,600</td><td>2,700</td></tr>
<tr><td class="text">Operating Profit</td><td>480</td><td>500</td><td>520</td><td>540</td></tr></tbody></table></section>
<section id="profit-loss"><table class="data-table"><thead><tr><th class="text"></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th><th>TTM</th></tr></thead><tbody>
<tr><td class="text"><button>Sales&nbsp;+</button></td><td>8,000</td><td>9,000</td><td>9,900</td><td>10,800</td><td>11,000</td></tr>
<tr><td class="text"><button>Expenses&nbsp;+</button></td><td>6,500</td><td>7,300</td><td>8,000</td><td>8,700</td><td>9,000</td></tr>
<tr><td class="text">Operating Profit</td><td>1,500</td><td>1,700</td><td>1,900</td><td>2,100</td><td>2,000</td></tr>
<tr><td class="text">Other Income&nbsp;+</td><td>50</td><td>60</td><td>70</td><td>80</td><td>80</td></tr>
<tr><td class="text">Interest</td><td>200</td><td>180</td><td>150</td><td>120</td><td>110</td></tr>
<tr><td class="text">Depreciation</td><td>300</td><td>320</td><td>340</td><td>360</td><td>360</td></tr>
<tr><td class="text">Profit before tax</td><td>1,050</td><td>1,260</td><td>1,480</td><td>1,700</td><td>1,600</td></tr>
<tr><td class="text">Net Profit&nbsp;+</td><td>790</td><td>945</td><td>1,110</td><td>1,275</td><td>1,200</td></tr></tbody></table></section>
<section id="balance-sheet"><table class="data-table"><thead><tr><th class="text"></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody>
<tr><td class="text">Equity Capital</td><td>100</td><td>100</td><td>100</td><td>100</td></tr>
<tr><td class="text">Reserves</td><td>3,900</td><td>4,500</td><td>5,300</td><td>6,200</td></tr>
<tr><td class="text">Borrowings&nbsp;+</td><td>2,000</td><td>1,800</td><td>1,500</td><td>1,200</td></tr></tbody></table></section>
<section id="cash-flow"><table class="data-table"><thead><tr><th class="text"></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody>
<tr><td class="text">Cash from Operating Activity&nbsp;+</td><td>900</td><td>1,000</td><td>1,150</td><td>1,300</td></tr>
<tr><td class="text">Cash from Investing Activity&nbsp;+</td><td>-600</td><td>-650</td><td>-700</td><td>-750</td></tr></tbody></table></section>
<section id="ratios"><table class="data-table"><thead><tr><th class="text"></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody>
<tr><td class="text">Debtor Days</td><td>60</td><td>58</td><td>55</td><td>52</td></tr>
<tr><td class="text">Inventory Days</td><td>40</td><td>40</td><td>38</td><td>36</td></tr>
<tr><td class="text">Days Payable</td><td>30</td><td>30</td><td>31</td><td>32</td></tr></tbody></table></section>
<section id="documents">
 <div class="documents annual-reports flex-column"><h3>Annual reports</h3><ul class="list-links">
  <li><a href="https://example.com/ar2026.pdf">Financial Year 2026 from bse</a></li><li><a href="https://example.com/ar2025.pdf">Financial Year 2025 from bse</a></li></ul></div>
 <div class="documents concalls flex-column"><h3>Concalls</h3><ul class="list-links">
  <li><div class="ink-600">Aug 2026</div><a class="concall-link" href="https://example.com/t1.pdf">Transcript</a><a href="https://example.com/p1.pdf">PPT</a></li>
  <li><div class="ink-600">May 2026</div><a class="concall-link" href="https://example.com/t2.pdf">Transcript</a></li>
  <li><div class="ink-600">Feb 2026</div><button>Notes</button></li></ul></div>
</section></body></html>"""

BANK_HTML = """<html><body><h1>Some Bank</h1><section id="profit-loss"><table><thead><tr><th></th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody>
<tr><td>Revenue</td><td>100</td><td>120</td></tr><tr><td>Financing Profit</td><td>30</td><td>36</td></tr><tr><td>Net Profit</td><td>20</td><td>25</td></tr></tbody></table></section>
<section id="balance-sheet"><table><thead><tr><th></th><th>Mar 2025</th><th>Mar 2026</th></tr></thead><tbody><tr><td>Deposits</td><td>900</td><td>1,000</td></tr><tr><td>Borrowing</td><td>50</td><td>60</td></tr></tbody></table></section></body></html>"""


def make_pdf(path: Path, pages: list[str]):
    import fitz
    doc = fitz.open()
    for t in pages:
        pg = doc.new_page()
        if t:
            pg.insert_textbox(fitz.Rect(54, 56, 541, 800), t, fontsize=10, fontname="helv")
    doc.save(str(path))
    doc.close()


@pytest.fixture(scope="module")
def db():
    init_db()
    s = SessionLocal()
    yield s
    set_setting(s, "data_mode", "demo")
    s.close()


# ---------------------------------------------------------------- screener parser
def test_screener_parser_financials_and_documents():
    r = cd.parse_screener_html(SCREENER_HTML)
    assert r["name"] == "Zenith Widgets Ltd" and not r["is_bank"]
    by = {(x["period"], x["metric"]): x["value"] for x in r["financials"]}
    assert by[("FY26", "revenue")] == 10800 and by[("FY26", "ebitda")] == 2100 and by[("FY26", "pat")] == 1275
    assert by[("FY26", "equity")] == 6300 and by[("FY26", "debt")] == 1200 and by[("FY26", "cfo")] == 1300 and by[("FY26", "investing_cf")] == -750
    assert by[("FY26", "receivable_days")] == 52
    assert ("TTM", "revenue") not in by and not any(p == "TTM" for p, _ in by)
    assert by[("Q2FY27", "revenue")] == 2700 and by[("Q1FY27", "ebitda")] == 520       # Sep 2026 = Q2 FY27
    assert [d["period"] for d in r["documents"]["annual_reports"]] == ["FY26", "FY25"]
    calls = r["documents"]["concalls"]
    assert len(calls) == 2 and calls[0]["period"] == "Q1FY27" and calls[1]["period"] == "Q4FY26"   # call with no transcript link is skipped


def test_screener_bank_drops_ebitda_and_debt():
    r = cd.parse_screener_html(BANK_HTML)
    assert r["is_bank"]
    metrics = {x["metric"] for x in r["financials"]}
    assert "ebitda" not in metrics and "debt" not in metrics and {"revenue", "pat"} <= metrics


# ---------------------------------------------------------------- PDF pipeline
def test_pdf_extraction_chunking_keeps_page_numbers(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["Page one talks about the widget business and its segments.\n" * 12, "Page two covers risk factors including raw material prices.\n" * 12])
    pages = pdf_extraction.extract_pages(p)
    assert len(pages) == 2 and "widget" in pages[0] and "risk" in pages[1]
    ch = di.chunk_pages(pages)
    assert {c["page"] for c in ch} == {1, 2} and all(len(c["text"]) > 40 for c in ch)


def test_scanned_pdf_is_reported_not_faked(db, tmp_path):
    p = tmp_path / "scan.pdf"
    make_pdf(p, ["", ""])
    doc = di.ingest_pdf(db, ticker="SCANTEST", path=p, doc_type="annual_report", title="Scanned AR")
    assert doc.status == "failed" and db.query(Chunk).filter_by(doc_id=doc.id).count() == 0


def test_ingestion_idempotent(db, tmp_path):
    p = tmp_path / "b.pdf"
    make_pdf(p, ["Revenue grew strongly this year due to volume growth across segments. " * 8])
    d1 = di.ingest_pdf(db, ticker="IDEMTEST", path=p, doc_type="annual_report", title="x")
    n = db.query(Chunk).filter_by(ticker="IDEMTEST").count()
    d2 = di.ingest_pdf(db, ticker="IDEMTEST", path=p, doc_type="annual_report", title="x")
    assert d1.id == d2.id and db.query(Chunk).filter_by(ticker="IDEMTEST").count() == n


def test_download_rejects_non_pdf(monkeypatch):
    import httpx

    class R:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def raise_for_status(s): pass
        def iter_bytes(s, n): yield b"<html>not a pdf</html>"
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: R())
    with pytest.raises(ValueError, match="did not return a PDF"):
        di.download_pdf("https://example.com/x", "ZZ")


# ---------------------------------------------------------------- guidance
def _chunk(text, cid, page=1):
    return SimpleNamespace(id=cid, text=text, page=page), SimpleNamespace(id=1, title="Call", period="Q4FY25", doc_date="2025-05-15", is_demo=False)


def test_guidance_explicit_vs_commentary_vs_historical():
    txt = ("We closed FY25 with revenue growth of 12.5% over last year. For FY26, we expect revenue growth of 9% to 11%. "
           "We are guiding for EBITDA margin of around 17.5% for FY26. Capex for FY26 is planned at approximately Rs. 12,500 crore. "
           "We plan to commission additional capacity next year. Margins benefited from mix this quarter.")
    items = gd.extract_guidance([_chunk(txt, 1)])
    kinds = {(i["metric"], i["kind"]) for i in items}
    assert ("revenue_growth", "explicit") in kinds and ("ebitda_margin", "explicit") in kinds and ("capex", "explicit") in kinds
    rg = [i for i in items if i["metric"] == "revenue_growth"]
    assert len(rg) == 1 and (rg[0]["low"], rg[0]["high"], rg[0]["fy"]) == (9.0, 11.0, "FY26")       # the past-tense 12.5% is NOT guidance
    assert next(i for i in items if i["metric"] == "capex")["low"] == 12500
    cap = next(i for i in items if i["metric"] == "capacity")
    assert cap["kind"] == "commentary" and cap["low"] is None                                          # qualitative stays qualitative
    assert not any("benefited from mix" in i["text"] for i in items)


def test_assessment_met_missed_tracking_pending():
    fin = {"annual": {"FY25": {"revenue": 1000, "ebitda": 150, "capex": 100}, "FY26": {"revenue": 1100, "ebitda": 165, "capex": 130}},
           "quarterly": {"Q1FY26": {"revenue": 270}, "Q2FY26": {"revenue": 280}, "Q1FY27": {"revenue": 300}, "Q2FY27": {"revenue": 310}}}
    mk = lambda m, fy, lo, hi=None: {"metric": m, "fy": fy, "low": lo, "high": hi}
    assert gd.assess(mk("revenue_growth", "FY26", 9, 11), fin)["status"] == "met"          # 10% growth
    assert gd.assess(mk("revenue_growth", "FY26", 12, 14), fin)["status"] == "missed"
    a = gd.assess(mk("revenue_growth", "FY27", 8, 10), fin)
    assert a["status"] == "tracking" and abs(a["actual"]["value"] - 10.9) < 0.1                 # H1 610 vs 550
    assert gd.assess(mk("ebitda_margin", "FY26", 15.0), fin)["status"] == "met"
    assert gd.assess(mk("ebitda_margin", "FY26", 17.0), fin)["status"] == "missed"
    assert gd.assess(mk("capex", "FY26", 120), fin)["status"] == "met"                      # 130 vs 120 = +8%
    assert gd.assess(mk("capex", "FY26", 100), fin)["status"] == "missed"
    assert gd.assess(mk("capex", "FY28", 100), fin)["status"] == "pending"
    assert gd.assess({"metric": "revenue_growth", "fy": None, "low": 5, "high": None}, fin)["status"] == "not_verifiable"


# ---------------------------------------------------------------- a company FINN has never seen
@pytest.fixture(scope="module")
def unseen(db, tmp_path_factory):
    """Live-mode company ZENITH built only from: a screener-shaped HTML fixture + two real PDFs."""
    set_setting(db, "data_mode", "live")
    parsed = cd.parse_screener_html(SCREENER_HTML)
    cd.store_financials(db, "ZENITH", parsed["financials"], "screener.in (fixture)", "https://www.screener.in/company/ZENITH/")
    d = tmp_path_factory.mktemp("docs")
    ar, cc = d / "ar.pdf", d / "call.pdf"
    make_pdf(ar, ["Zenith Widgets Ltd - Annual Report FY26\n\nBusiness overview\nZenith Widgets manufactures industrial widgets and sells them to automotive customers across India and Europe.\n"
                  "Segment revenue mix\nIndustrial Widgets - 70%\nAutomotive Widgets - 30%\n\nEBITDA margin was 19.4% in FY26 compared with 19.0% in FY25 due to operating leverage.",
                  "Risks and concerns\n1. Raw material price volatility affecting steel inputs. Reviewed quarterly by the committee.\n2. Customer concentration in the automotive segment. Mitigation is ongoing.\n"
                  "Contingent liabilities amounted to Rs. 420 crore as at 31 March 2026.\nThe auditors have issued an unmodified opinion."])
    make_pdf(cc, ["Zenith Widgets Q4 FY25 earnings call\nCFO: For FY26, we expect revenue growth of 12% to 14%. We are guiding for EBITDA margin of around 20.5% for FY26.\n"
                  "CFO: Capex for FY26 is planned at approximately Rs. 200 crore."])
    di.ingest_pdf(db, ticker="ZENITH", path=ar, doc_type="annual_report", title="Zenith Annual Report FY26", period="FY26", source_url="https://example.com/ar2026.pdf")
    di.ingest_pdf(db, ticker="ZENITH", path=cc, doc_type="concall", title="Zenith Q4FY25 call", period="Q4FY25", doc_date="2025-05-20", source_url="https://example.com/t.pdf")
    yield "ZENITH"
    set_setting(db, "data_mode", "demo")


def test_research_works_on_unseen_ticker(db, unseen):
    rep = ra.build_report(db, unseen, demo=False)
    S = rep["sections"]
    assert rep["status"] == "ok" and rep["mode"] == "live" and rep["data_label"] is None
    assert [s["name"] for s in S["business"]["segments"]] == ["Industrial Widgets", "Automotive Widgets"]
    a = S["snapshot"]["annual"]
    assert a["period"] == "FY26" and a["revenue"] == 10800 and a["ebitda_margin"] == pytest.approx(19.44, abs=0.01)
    assert a["debt_to_equity"] == pytest.approx(0.19, abs=0.01) and a["pat_yoy"]["pct"] == pytest.approx(14.86, abs=0.01)
    assert S["cash_quality"]["series"][-1]["fcf"] == 1300 - 750                                  # capex missing -> investing-CF proxy, flagged
    assert "proxy" in S["cash_quality"]["note"]
    rows = {(r["metric"], r["fy"]): r for r in S["narrative"]["rows"]}
    assert rows[("revenue_growth", "FY26")]["status"] == "missed"                              # guided 12-14%, reported 9.1%
    assert rows[("ebitda_margin", "FY26")]["status"] == "missed"                               # guided 20.5, reported 19.4
    assert rows[("capex", "FY26")]["status"] == "not_verifiable"                               # no capex in this company's data -> says so
    flags = {f["kind"]: f for f in S["risks"]["flags"]}
    assert "420" in flags["contingent_liabilities"]["label"] and flags["auditor"]["status"] == "clean"
    assert [r["text"] for r in S["risks"]["risks"]][0].startswith("Raw material price volatility")
    # every guidance row cites the transcript page
    assert all(r["citation"]["url"].endswith("#page=1") for r in S["narrative"]["rows"])
    assert S["bull_bear"]["bull"] and S["bull_bear"]["bear"]
    for side in ("bull", "bear"):
        assert all(p["evidence"] for p in S["bull_bear"][side])                                  # no claim without evidence


def test_retrieval_relevance_and_nonsense(db, unseen):
    h = retrieval.search(db, unseen, "customer concentration risk automotive", is_demo=False)
    assert h and "Customer concentration" in h[0].text and h[0].page == 2 and h[0].citation()["url"].endswith("#page=2")
    assert retrieval.search(db, unseen, "quantum chromodynamics lagrangian", is_demo=False) == []
    assert retrieval.search(db, unseen, "customer concentration", is_demo=True) == []            # demo/live corpora never mix


def test_copilot_on_unseen_company_cites_and_refuses(db, unseen):
    r = copilot.answer(db, unseen, "Why did the EBITDA margin change?")
    assert "operating leverage" in r["answer"] and r["citations"] and not r["insufficient"]
    g = copilot.answer(db, unseen, "Has management achieved its previous growth guidance?")
    assert "missed" in g["answer"] and g["table"]
    out = copilot.answer(db, unseen, "What is the capital of France?")
    assert out["insufficient"] and out["citations"] == []
    none = copilot.answer(db, "NODOCS", "What are the key risks?")
    assert none["insufficient"] and "Insufficient evidence" in none["answer"]


def test_llm_output_is_verified_before_use(db, unseen):
    class Fake(llm_mod.LLMProvider):
        name, model = "fake", "m"
        def __init__(self, text): self.text = text
        def available(self): return True
        def generate(self, *a, **k): return self.text
    try:
        llm_mod._provider = Fake("EBITDA margin rose to 25.0% because of pricing power [1].")          # 25.0 and 'pricing' are not in the sources
        bad = copilot.answer(db, unseen, "Why did the EBITDA margin change?")
        assert "25.0" not in bad["answer"] and "rejected" in bad["generated_by"]
        llm_mod._provider = Fake("Per the company, margin was 19.4% in FY26 versus 19.0% in FY25 due to operating leverage [2].")
        good = copilot.answer(db, unseen, "Why did the EBITDA margin change?")
        assert "verified" in good["generated_by"] and "19.4%" in good["answer"]
        llm_mod._provider = Fake("It went up [9].")                                                  # citation to a non-existent source
        ref = copilot.answer(db, unseen, "Why did the EBITDA margin change?")
        assert "[9]" not in ref["answer"]
    finally:
        llm_mod.reset_llm()


def test_results_parser_handles_label_and_numbers_on_separate_lines():
    from app.services.announcement_extractors import extract_results
    pdf_like = """Statement of Consolidated Financial Results
(Rs. in crore)
Particulars
30.09.2026
30.06.2026
30.09.2025
Revenue from operations
1,000
900
800
Profit before tax
200
180
150
Profit for the period
150
135
110
"""
    r = extract_results(pdf_like)
    assert r and r["metrics"]["revenue"]["current"] == 1000 and r["metrics"]["pat"]["yoy"]["pct"] == pytest.approx(36.36, abs=0.01)


def test_followup_inherits_topic_but_unrelated_question_does_not():
    from app.services.copilot import detect_intent
    assert detect_intent("What about the previous year?", "guidance") == "guidance"
    assert detect_intent("Can you explain that in more detail?", "cash") == "cash"
    assert detect_intent("And Q2?", "quarters") == "quarters"
    assert detect_intent("What is the capital of France?", "guidance") is None
    assert detect_intent("Who won the cricket match yesterday?", "risks") is None
    assert detect_intent("Has management met its guidance?", None) == "guidance"
