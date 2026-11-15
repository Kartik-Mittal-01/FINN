"""Alert evaluation. Rules come from the user's settings; output is an in-app notification feed.
Idempotent: each alert has a deterministic dedupe key, and alerts that no longer satisfy the current settings are removed
so changing a threshold visibly changes the feed."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import Alert, Announcement, Holding, utcnow
from . import market_data
from .prioritisation import PRIORITY_ORDER
from .state import get_alert_settings, is_demo

log = logging.getLogger(__name__)


def evaluate(db: Session) -> dict:
    cfg = get_alert_settings(db)
    demo = is_demo(db)
    desired: dict[str, dict] = {}
    if cfg["enabled"]:
        held = [h.ticker for h in db.query(Holding).all()]
        monitored = [t for t in held if not cfg["tickers"] or t in cfg["tickers"]]
        for t in monitored:
            st = market_data.stats(db, t)
            if not st or not st.get("available"):
                continue
            chg, vr, asof = st["change_pct"], st["volume_ratio"], st["as_of"]
            hit_px = chg is not None and abs(chg) >= cfg["price_threshold_pct"]
            hit_vol = vr is not None and vr >= cfg["volume_multiple"]
            if hit_px:
                desired[f"px:{t}:{asof}"] = dict(ticker=t, kind="price_move", severity="high" if abs(chg) >= cfg["price_threshold_pct"] * 1.5 else "medium",
                    title=f"{t} {chg:+.1f}% in a day", detail=f"Close ₹{st['close']:,.2f} vs ₹{st['prev_close']:,.2f}. Threshold ±{cfg['price_threshold_pct']}%. End-of-day data as of {asof}.")
            if hit_vol:
                desired[f"vol:{t}:{asof}"] = dict(ticker=t, kind="volume_spike", severity="high" if hit_px else "medium",
                    title=f"{t} volume {vr:.1f}× its 20-day average", detail=f"Volume {st['volume']:,.0f} vs 20-day avg {st['avg_volume_20d']:,.0f}. Threshold {cfg['volume_multiple']}×. End-of-day data as of {asof}.")
        cutoff = utcnow() - timedelta(days=7)
        min_rank = PRIORITY_ORDER[cfg["min_priority"]]
        for a in db.query(Announcement).filter(Announcement.filed_at >= cutoff, Announcement.is_demo == demo).all():
            if a.ticker not in monitored or a.category not in cfg["categories"] or PRIORITY_ORDER.get(a.priority, 0) < min_rank:
                continue
            desired[f"ann:{a.id}"] = dict(ticker=a.ticker, kind="announcement", severity=a.priority, announcement_id=a.id,
                title=f"{a.ticker}: {a.category.replace('_', ' ')} – {a.headline[:90]}", detail=(a.summary_what or a.headline)[:240])
    existing = {x.dedupe_key: x for x in db.query(Alert).filter(Alert.is_demo == demo).all()}
    removed = 0
    for k, x in existing.items():
        if k not in desired:
            db.delete(x)
            removed += 1
    created = 0
    for k, v in desired.items():
        if k not in existing:
            db.add(Alert(dedupe_key=k, is_demo=demo, **v))
            created += 1
    db.commit()
    return {"created": created, "removed": removed, "active": len(desired)}
