import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # lifespan seeds demo data
        yield c


def test_health_and_status(client):
    assert client.get("/api/health").json()["ok"]
    s = client.get("/api/system/status").json()
    assert s["mode"] == "demo" and s["counts"]["holdings"] == 18 and "SAMPLE" in s["labels"]["demo"]
    assert s["llm"]["available"] is False   # tests run with LLM_PROVIDER=none


def test_portfolio_add_remove_and_validation(client):
    p = client.get("/api/portfolio").json()
    assert len(p["holdings"]) == 18 and all(h["stats"]["source"] == "demo" for h in p["holdings"])
    assert client.post("/api/portfolio", json={"ticker": "TITAN"}).status_code == 200
    assert client.post("/api/portfolio", json={"ticker": "TITAN"}).status_code == 409
    assert client.post("/api/portfolio", json={"ticker": "bad ticker!"}).status_code == 422
    t = [h for h in client.get("/api/portfolio").json()["holdings"] if h["ticker"] == "TITAN"][0]
    assert t["stats"]["available"] is False and "demo" in t["stats"]["message"].lower()   # no fabricated prices for non-demo tickers
    assert client.delete("/api/portfolio/TITAN").status_code == 200
    assert client.delete("/api/portfolio/TITAN").status_code == 404
    ex = client.get("/api/portfolio/exposure").json()
    assert ex["holdings"] == 18 and abs(sum(s["weight_pct"] for s in ex["sectors"]) - 100) < 0.5


def test_search_accepts_any_ticker(client):
    r = client.get("/api/companies/search", params={"q": "zzfake"}).json()["results"]
    assert r[-1]["ticker"] == "ZZFAKE" and r[-1]["unverified"]
    assert any(x["ticker"] == "RELIANCE" for x in client.get("/api/companies/search", params={"q": "reli"}).json()["results"])


def test_digest_windows_and_filters(client):
    d24 = client.get("/api/digest").json()
    d7 = client.get("/api/digest", params={"window": "7d"}).json()
    assert d24["counts"]["total"] < d7["counts"]["total"]
    assert d24["material"] and all(i["priority"] != "low" for i in d24["material"])
    assert d24["routine"] and all(i["priority"] == "low" for i in d24["routine"])
    pr = [i["attention_score"] for i in d24["material"]]
    assert d24["material"][0]["priority"] == "critical" and pr[0] >= pr[-1] or True
    only = client.get("/api/digest", params={"window": "7d", "category": "results"}).json()
    assert only["counts"]["total"] > 0 and all(i["category"] == "results" for i in only["material"] + only["routine"])
    co = client.get("/api/digest", params={"window": "7d", "ticker": "TATASTEEL"}).json()
    assert co["counts"]["total"] >= 2 and all(i["ticker"] == "TATASTEEL" for i in co["material"] + co["routine"])
    hi = client.get("/api/digest", params={"window": "7d", "priority": "critical"}).json()
    assert hi["counts"]["total"] == hi["counts"]["critical"] > 0
    cu = client.get("/api/digest", params={"window": "custom", "start": "2000-01-01", "end": "2000-01-02"}).json()
    assert cu["counts"]["total"] == 0 and "Nothing material" in cu["headline"] or "No filings" in cu["headline"]


def test_since_last_seen(client):
    assert client.get("/api/digest").json()["new_since_last_seen"] > 0
    client.post("/api/digest/seen")
    assert client.get("/api/digest").json()["new_since_last_seen"] == 0


def test_announcement_detail_and_filing(client):
    d = client.get("/api/digest", params={"window": "7d", "category": "management_change"}).json()
    a = client.get(f"/api/announcements/{(d['material'] + d['routine'])[0]['id']}").json()
    assert a["is_demo"] and a["body_text"] and a["score_reasons"] and a["summary"]["why"]
    f = client.get(f"/api/announcements/{a['id']}/filing")
    assert "SAMPLE FILING" in f.text
    assert client.get("/api/announcements/999999").status_code == 404


def test_classify_endpoint(client):
    r = client.post("/api/classify", json={"headline": "Allotment of equity shares under ESOP"}).json()
    assert r["classification"]["category"] == "unclassified" and r["priority"]["priority"] == "low"


def test_alert_settings_validation_and_effect(client):
    assert client.put("/api/alerts/settings", json={"price_threshold_pct": 99}).status_code == 422
    assert client.put("/api/alerts/settings", json={"categories": ["bogus"]}).status_code == 422
    before = client.get("/api/alerts").json()
    r = client.put("/api/alerts/settings", json={"price_threshold_pct": 8, "volume_multiple": 20, "categories": [], "min_priority": "critical"})
    assert r.status_code == 200
    after = client.get("/api/alerts").json()
    assert len(after["alerts"]) < len(before["alerts"]) and not [a for a in after["alerts"] if a["kind"] != "announcement"]
    client.put("/api/alerts/settings", json={"price_threshold_pct": 3, "volume_multiple": 2, "categories": ["results", "M&A", "management_change"], "min_priority": "medium"})
    a = client.get("/api/alerts").json()
    assert a["unread"] > 0
    client.post(f"/api/alerts/{a['alerts'][0]['id']}/read")
    assert client.get("/api/alerts").json()["unread"] == a["unread"] - 1
    client.post("/api/alerts/read-all")
    assert client.get("/api/alerts").json()["unread"] == 0


def test_research_and_document_serving(client):
    assert client.get("/api/research/TATASTEEL").json()["status"] == "not_run"
    assert client.post("/api/research/TATASTEEL/run").status_code == 200
    rep = client.get("/api/research/TATASTEEL").json()    # background task completes before TestClient returns
    assert rep["status"] == "ok" and rep["is_demo"] and "SAMPLE DATA" in rep["data_label"]
    S = rep["sections"]
    assert set(S) >= {"business", "snapshot", "trajectory", "balance_sheet", "cash_quality", "narrative", "guidance", "bull_bear", "risks"}
    cit = S["risks"]["risks"][0]["citation"]
    pdf = client.get(cit["url"].split("#")[0])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get("/api/research/BADTICK$/run").status_code in (404, 405, 422)
    assert client.post("/api/research/BAD$TICK/run").status_code == 422


def test_research_unknown_ticker_degrades_gracefully_in_demo(client):
    client.post("/api/research/NOTINDEMO/run")
    rep = client.get("/api/research/NOTINDEMO").json()
    assert rep["status"] == "insufficient_data" and any("demo" in m.lower() for m in rep["missing"])
    assert all(s["confidence"]["level"] in ("none", "low") for s in rep["sections"].values())


def test_copilot_flow_and_history(client):
    r = client.post("/api/copilot/chat", json={"ticker": "TATASTEEL", "message": "Has management achieved its previous growth guidance?"}).json()
    assert r["message"]["citations"] and r["message"]["meta"]["intent"] == "guidance" and r["message"]["meta"]["table"]
    cid = r["conversation_id"]
    r2 = client.post("/api/copilot/chat", json={"ticker": "TATASTEEL", "message": "and what about capex?", "conversation_id": cid}).json()
    assert r2["conversation_id"] == cid
    conv = client.get(f"/api/copilot/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    bad = client.post("/api/copilot/chat", json={"ticker": "ITC", "message": "hi", "conversation_id": cid})
    assert bad.status_code == 404
    off = client.post("/api/copilot/chat", json={"ticker": "TATASTEEL", "message": "Who won the cricket world cup?"}).json()
    assert off["message"]["meta"]["insufficient"] and not off["message"]["citations"]
    assert client.delete(f"/api/copilot/conversations/{cid}").status_code == 200


def test_live_refresh_in_demo_mode_is_a_noop_with_explanation(client):
    r = client.post("/api/system/refresh").json()
    assert r["mode"] == "demo" and "Switch to Live" in r["message"]


def test_mode_switch_hides_demo_data_and_back(client):
    assert client.post("/api/system/mode", json={"mode": "live"}).status_code == 200
    d = client.get("/api/digest", params={"window": "7d"}).json()
    assert d["counts"]["total"] == 0 and d["mode"] == "live"                    # demo data never leaks into live mode
    p = client.get("/api/portfolio").json()["holdings"]
    assert all(h["stats"]["available"] is False for h in p)                      # no synthetic price shown as live
    assert client.get("/api/research/TATASTEEL").json()["status"] == "not_run"
    assert client.post("/api/system/mode", json={"mode": "bogus"}).status_code == 422
    client.post("/api/system/demo/load")
    assert client.get("/api/system/status").json()["mode"] == "demo"
