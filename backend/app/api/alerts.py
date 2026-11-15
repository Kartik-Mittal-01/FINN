from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert
from ..services import alert_engine
from ..services.announcement_classifier import CATEGORIES
from ..services.state import get_alert_settings, is_demo, set_setting
from .deps import iso

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertSettingsIn(BaseModel):
    enabled: bool = True
    price_threshold_pct: float = Field(3.0, ge=0.5, le=25)
    volume_multiple: float = Field(2.0, ge=1.0, le=20)
    categories: list[str] = []
    min_priority: str = "medium"
    tickers: list[str] = []

    @field_validator("categories")
    @classmethod
    def _cats(cls, v):
        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown categories: {bad}")
        return v

    @field_validator("min_priority")
    @classmethod
    def _prio(cls, v):
        if v not in ("critical", "high", "medium", "low"):
            raise ValueError("min_priority must be critical|high|medium|low")
        return v


def _out(a: Alert):
    return {"id": a.id, "ticker": a.ticker, "kind": a.kind, "severity": a.severity, "title": a.title, "detail": a.detail,
            "announcement_id": a.announcement_id, "created_at": iso(a.created_at), "read": a.read, "is_demo": a.is_demo}


@router.get("")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.query(Alert).filter(Alert.is_demo == is_demo(db)).order_by(Alert.read, Alert.id.desc()).all()
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda a: (a.read, rank.get(a.severity, 9)))
    return {"alerts": [_out(a) for a in rows], "unread": sum(not a.read for a in rows)}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {"settings": get_alert_settings(db), "all_categories": CATEGORIES}


@router.put("/settings")
def put_settings(body: AlertSettingsIn, db: Session = Depends(get_db)):
    set_setting(db, "alert_settings", body.model_dump())
    res = alert_engine.evaluate(db)
    return {"settings": get_alert_settings(db), "evaluation": res}


@router.post("/evaluate")
def evaluate(db: Session = Depends(get_db)):
    return alert_engine.evaluate(db)


@router.post("/read-all")
def read_all(db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.is_demo == is_demo(db)).update({"read": True})
    db.commit()
    return {"ok": True}


@router.post("/{aid}/read")
def read_one(aid: int, db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if not a:
        raise HTTPException(404, "Alert not found")
    a.read = True
    db.commit()
    return _out(a)
