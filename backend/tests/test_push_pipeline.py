import pytest
from datetime import datetime, timedelta

from app.database import init_db, SessionLocal
from app.models import Alert, Announcement, Holding, PriceBar
from app.services import alert_engine, demo_seed, market_data
from app.services.state import set_setting, get_alert_settings


@pytest.fixture(scope="module")
def db():
    init_db()
    s = SessionLocal()
    demo_seed.seed_demo(s)
    yield s
    s.close()


def test_seed_is_idempotent(db):
    n1 = db.query(Announcement).count(), db.query(PriceBar).count(), db.query(Holding).count()
    demo_seed.seed_demo(db)
    n2 = db.query(Announcement).count(), db.query(PriceBar).count(), db.query(Holding).count()
    assert n1 == n2 and n1[2] == 18


def test_everything_seeded_is_labelled_demo(db):
    assert db.query(Announcement).filter(Announcement.is_demo == False).count() == 0  # noqa
    assert db.query(Announcement).filter(Announcement.source != "demo").count() == 0
    assert db.query(PriceBar).filter(PriceBar.source != "demo").count() == 0


def test_digest_window_contents_and_priorities(db):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    last24 = db.query(Announcement).filter(Announcement.filed_at >= cutoff).all()
    assert len(last24) >= 12
    cats = {a.category for a in last24}
    assert {"results", "management_change", "capex", "unclassified"} <= cats
    top = max(last24, key=lambda a: a.attention_score)
    assert top.priority == "critical"
    routine = [a for a in last24 if a.category == "unclassified"]
    assert routine and all(a.priority == "low" for a in routine)


def test_results_have_structured_numbers(db):
    a = db.query(Announcement).filter_by(ticker="TATASTEEL", category="results").first()
    m = a.extracted["metrics"]
    assert m["revenue"]["current"] and m["pat"]["yoy"]["pct"] is not None and m["ebitda"]["derived"] is True
    bank = db.query(Announcement).filter_by(ticker="ICICIBANK", category="results").first()
    assert bank.extracted["metrics"]["ebitda"]["current"] is None  # banks: unavailable, not invented


def test_bond_issue_is_fund_raise(db):
    a = db.query(Announcement).filter(Announcement.ticker == "SBIN", Announcement.headline.like("%Non-Convertible Bonds%")).first()
    assert a.category == "fund_raise" and a.priority in ("high", "critical")


def test_market_stats(db):
    st = market_data.stats(db, "TATASTEEL")
    assert st["available"] and st["source"] == "demo" and st["note"].startswith("End-of-day")
    assert st["change_pct"] == pytest.approx(4.1, abs=0.15) and st["volume_ratio"] == pytest.approx(2.8, abs=0.15)
    assert len(st["spark"]) == 30
    assert market_data.stats(db, "NOSUCHTICKER")["available"] is False


def test_alert_thresholds_are_live(db):
    base = alert_engine.evaluate(db)
    px = lambda: {a.ticker for a in db.query(Alert).filter(Alert.kind == "price_move")}
    assert "TATASTEEL" in px() and "ETERNAL" in px()
    cfg = get_alert_settings(db)
    set_setting(db, "alert_settings", {**cfg, "price_threshold_pct": 5.0})
    alert_engine.evaluate(db)
    assert px() == {"ETERNAL"}                       # 4.1% / -3.4% no longer qualify at 5%
    set_setting(db, "alert_settings", {**cfg, "price_threshold_pct": 3.0, "volume_multiple": 3.0})
    alert_engine.evaluate(db)
    vol = {a.ticker for a in db.query(Alert).filter(Alert.kind == "volume_spike")}
    assert vol == {"ETERNAL"}
    set_setting(db, "alert_settings", {**cfg, "categories": ["management_change"], "min_priority": "low"})
    alert_engine.evaluate(db)
    anns = db.query(Alert).filter(Alert.kind == "announcement").all()
    assert anns and all("management" in a.title for a in anns)
    set_setting(db, "alert_settings", {**cfg, "enabled": False})
    alert_engine.evaluate(db)
    assert db.query(Alert).count() == 0
    set_setting(db, "alert_settings", cfg)
    alert_engine.evaluate(db)
    assert db.query(Alert).count() == base["active"]


def test_alert_evaluation_is_idempotent(db):
    alert_engine.evaluate(db)
    n = db.query(Alert).count()
    r = alert_engine.evaluate(db)
    assert db.query(Alert).count() == n and r["created"] == 0
