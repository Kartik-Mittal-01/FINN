"""Tiny key-value settings store + data-mode helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULT_ALERT_SETTINGS = {
    "enabled": True,
    "price_threshold_pct": 3.0,
    "volume_multiple": 2.0,
    "categories": ["results", "M&A", "management_change", "fund_raise", "litigation", "credit_rating"],
    "min_priority": "medium",
    "tickers": [],  # empty = every holding
}


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def set_setting(db: Session, key: str, value: Any):
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_mode(db: Session) -> str:
    return get_setting(db, "data_mode", "demo")


def is_demo(db: Session) -> bool:
    return get_mode(db) == "demo"


def price_source(db: Session) -> str:
    return "demo" if is_demo(db) else "yfinance"


def get_alert_settings(db: Session) -> dict:
    return {**DEFAULT_ALERT_SETTINGS, **(get_setting(db, "alert_settings", {}) or {})}
