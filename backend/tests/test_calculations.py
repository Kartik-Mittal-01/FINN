import math
from app.services import financial_calculations as fc


def test_growth_basic():
    assert fc.pct_change(110, 100) == 10.0
    assert fc.pct_change(90, 100) == -10.0


def test_growth_edge_cases_never_return_fake_numbers():
    assert fc.growth(10, 0)["pct"] is None and "zero" in fc.growth(10, 0)["note"]
    assert fc.growth(None, 5)["pct"] is None
    assert fc.growth(5, None)["pct"] is None
    g = fc.growth(50, -20)
    assert g["pct"] is None and "turnaround" in g["note"]
    assert fc.growth(-5, -20)["pct"] is None
    assert fc.growth(float("nan"), 3)["pct"] is None


def test_margins_and_ratios():
    assert fc.ebitda_margin(25, 100) == 25.0
    assert fc.pat_margin(10, 200) == 5.0
    assert fc.ebitda_margin(10, 0) is None
    assert fc.debt_to_equity(50, 100) == 0.5
    assert fc.debt_to_equity(50, -10) is None
    assert fc.roe(20, 100) == 20.0
    assert fc.roe(20, 100, 60) == 25.0  # average equity 80
    assert fc.roce(pbt=30, interest=10, equity=100, debt=100) == 20.0


def test_cash_metrics():
    assert fc.free_cash_flow(100, 40) == 60
    assert fc.free_cash_flow(100, -40) == 60  # capex sign-agnostic
    assert fc.free_cash_flow(None, 40) is None
    assert fc.cfo_to_pat(80, 100) == 0.8
    assert fc.cfo_to_pat(80, 0) is None
    assert fc.cfo_to_pat(80, -5) is None


def test_volume_deviation():
    prior = [100] * 20
    r = fc.volume_deviation(250, prior)
    assert r["avg"] == 100 and r["ratio"] == 2.5 and r["pct"] == 150.0
    assert fc.volume_deviation(250, [100, 100])["ratio"] is None  # too little history


def test_cagr_and_trend():
    assert fc.cagr(100, 121, 2) == 10.0
    assert fc.cagr(0, 100, 2) is None
    assert fc.trend_label(100, 200, 3) == "growing"
    assert fc.trend_label(100, 101, 3) == "stagnant"
    assert fc.trend_label(100, 80, 3) == "deteriorating"


def test_unit_conversion():
    assert fc.convert_to_crore(1000, "lakh") == 10
    assert fc.convert_to_crore(1000, "million") == 100
    assert fc.convert_to_crore(5, "crore") == 5
    assert fc.convert_to_crore(None, "crore") is None


def test_volatility_needs_history():
    assert fc.annualised_volatility([100, 101]) is None
    closes = [100 * (1 + 0.01 * ((-1) ** i)) for i in range(40)]
    v = fc.annualised_volatility(closes)
    assert v is not None and v > 0 and not math.isnan(v)
