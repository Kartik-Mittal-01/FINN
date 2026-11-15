"""Seeds clearly-labelled SYNTHETIC demo data and runs it through the *real* pipelines
(classifier, extractors, priority engine, PDF ingestion, alert engine). Idempotent: safe to run repeatedly."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..demo import generator as G
from ..demo.universe import UNIVERSE, EXTRA_TICKERS
from ..models import Alert, Announcement, Company, Financial, Holding, PriceBar, ResearchReport
from . import alert_engine, announcement_ingestion as ai, document_ingestion as di
from .state import get_setting, set_setting

log = logging.getLogger(__name__)


def seed_demo(db: Session, *, with_documents: bool = True) -> dict:
    # 1. companies + default portfolio
    for u in UNIVERSE:
        co = db.get(Company, u["ticker"]) or Company(ticker=u["ticker"])
        co.name, co.sector, co.size_bucket, co.is_demo = u["name"], u["sector"], u["size"], True
        db.add(co)
    for t, name, sector in EXTRA_TICKERS:
        if not db.get(Company, t):
            db.add(Company(ticker=t, name=name, sector=sector, size_bucket="large", is_demo=True))
    db.commit()
    if db.query(Holding).count() == 0:
        for u in UNIVERSE:
            db.add(Holding(ticker=u["ticker"], kind="portfolio"))
        db.commit()

    # 2. prices (synthetic EOD bars)
    db.query(PriceBar).filter_by(source="demo").delete()
    n_bars = 0
    for u in UNIVERSE:
        for b in G.generate_prices(u):
            db.add(PriceBar(**b))
            n_bars += 1
    db.commit()

    # 3. financials (synthetic)
    db.query(Financial).filter_by(is_demo=True).delete()
    fins = {}
    for u in UNIVERSE:
        fin = G.generate_financials(u)
        fins[u["ticker"]] = fin
        for r in G.financial_rows(u["ticker"], fin):
            db.add(Financial(**r, unit="INR_crore", source="DEMO (synthetic)", source_url=None, is_demo=True))
    db.commit()

    # 4. documents: real PDFs with synthetic text, ingested via the normal PDF pipeline
    n_docs = 0
    if with_documents:
        for u in UNIVERSE:
            di.delete_documents(db, u["ticker"], is_demo=True)
            for d in G.generate_documents(u, fins[u["ticker"]], settings.documents_dir):
                doc = di.ingest_pdf(db, ticker=u["ticker"], path=d["path"], doc_type=d["doc_type"], title=d["title"], period=d["period"],
                                    doc_date=d["doc_date"], source_url=None, is_demo=True)
                n_docs += 1
        db.query(ResearchReport).filter_by(is_demo=True).delete()
        db.commit()

    # 5. announcements via the real pipeline
    db.query(Announcement).filter_by(is_demo=True).delete()
    db.query(Alert).filter_by(is_demo=True).delete()
    db.commit()
    now = datetime.utcnow()
    res = ai.ingest(db, ai.DemoConnector(fins), [], (now - timedelta(days=8)).date(), now.date())
    # filing view link for demo items (served by the API as plain text)
    for a in db.query(Announcement).filter_by(is_demo=True).all():
        a.url = f"/api/announcements/{a.id}/filing"
    db.commit()

    # simulate a previous visit 14h ago so the "since your last visit" strip is demonstrable (demo only)
    set_setting(db, "last_digest_seen", (now - timedelta(hours=14)).isoformat() + "Z")

    # 6. alerts
    al = alert_engine.evaluate(db)
    if get_setting(db, "data_mode") is None:
        set_setting(db, "data_mode", "demo")
    return {"companies": len(UNIVERSE), "price_bars": n_bars, "documents": n_docs, "announcements": res["ingested"], "alerts": al["active"]}


def ensure_seeded(db: Session):
    if db.query(Company).count() == 0:
        log.info("Empty database – seeding labelled demo data")
        seed_demo(db)
