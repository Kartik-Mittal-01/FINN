from datetime import datetime, timedelta
from typing import Optional

from ..models import Announcement


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def ann_out(a: Announcement, last_seen: Optional[str] = None, detail: bool = False) -> dict:
    d = {
        "id": a.id, "ticker": a.ticker, "company_name": a.company_name, "headline": a.headline, "filed_at": iso(a.filed_at), "exchange": a.exchange,
        "source": a.source, "is_demo": a.is_demo, "url": a.url, "attachment_url": a.attachment_url,
        "category": a.category, "category_confidence": a.category_confidence, "classifier": a.classifier,
        "priority": a.priority, "attention_score": a.attention_score, "score_reasons": a.score_reasons or [],
        "summary": {"what": a.summary_what, "why": a.summary_why, "watch": a.summary_watch, "by": a.summary_by},
        "extracted": a.extracted, "is_new": bool(last_seen and iso(a.filed_at) > last_seen),
    }
    if detail:
        d["body_text"] = a.body_text
        d["classifier_reasons"] = a.classifier_reasons or []
    return d


def window_bounds(window: str, start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime, str]:
    now = datetime.utcnow()
    if window == "custom" and start:
        s = datetime.fromisoformat(start[:10])
        e = (datetime.fromisoformat(end[:10]) if end else now) + timedelta(days=1) if end else now
        return s, e, f"{start[:10]} → {(end or now.date().isoformat())[:10]}"
    hours = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}.get(window, 24)
    label = {"24h": "Last 24 hours", "3d": "Last 3 days", "7d": "Last 7 days", "30d": "Last 30 days"}.get(window, "Last 24 hours")
    return now - timedelta(hours=hours), now, label
