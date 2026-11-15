from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Message
from ..services import copilot as cp
from ..services.state import is_demo
from .deps import iso

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class ChatIn(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[int] = None


def _msg(m: Message):
    return {"id": m.id, "role": m.role, "content": m.content, "citations": m.citations or [], "meta": m.meta or {}, "created_at": iso(m.created_at)}


@router.get("/suggestions")
def suggestions():
    return {"suggestions": cp.SUGGESTIONS}


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    t = body.ticker.strip().upper()
    conv = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if body.conversation_id and (not conv or conv.ticker != t):
        raise HTTPException(404, "Conversation not found for this company")
    if not conv:
        conv = Conversation(ticker=t, title=body.message[:60])
        db.add(conv)
        db.commit()
    history = [{"role": m.role, "content": m.content, "meta": m.meta or {}} for m in db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id).all()]
    db.add(Message(conversation_id=conv.id, role="user", content=body.message))
    res = cp.answer(db, t, body.message, history)
    meta = {k: res.get(k) for k in ("generated_by", "verified", "intent", "insufficient", "is_demo", "table")}
    m = Message(conversation_id=conv.id, role="assistant", content=res["answer"], citations=res["citations"], meta=meta)
    db.add(m)
    db.commit()
    return {"conversation_id": conv.id, "message": _msg(m), "suggestions": res.get("suggestions")}


@router.get("/conversations")
def conversations(ticker: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Conversation)
    if ticker:
        q = q.filter_by(ticker=ticker.upper())
    return {"conversations": [{"id": c.id, "ticker": c.ticker, "title": c.title, "created_at": iso(c.created_at)} for c in q.order_by(Conversation.id.desc()).limit(30)]}


@router.get("/conversations/{cid}")
def conversation(cid: int, db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found")
    return {"id": c.id, "ticker": c.ticker, "title": c.title, "messages": [_msg(m) for m in db.query(Message).filter_by(conversation_id=cid).order_by(Message.id)]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found")
    db.query(Message).filter_by(conversation_id=cid).delete()
    db.delete(c)
    db.commit()
    return {"deleted": cid}
