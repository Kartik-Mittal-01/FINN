"""SQLAlchemy models. Every record that can be synthetic carries `is_demo` so the UI can label it."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        UniqueConstraint, Index)

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(JSON)


class Company(Base):
    __tablename__ = "companies"
    ticker = Column(String(24), primary_key=True)          # NSE symbol, e.g. RELIANCE, M&M
    name = Column(String(160), nullable=False)
    sector = Column(String(64))
    size_bucket = Column(String(16))                       # large | mid | small
    bse_code = Column(String(12))
    verified = Column(Boolean, default=False)              # True once confirmed against a live source
    is_demo = Column(Boolean, default=False)


class Holding(Base):
    __tablename__ = "holdings"
    ticker = Column(String(24), ForeignKey("companies.ticker"), primary_key=True)
    kind = Column(String(12), default="portfolio")         # portfolio | watchlist
    added_at = Column(DateTime, default=utcnow)


class PriceBar(Base):
    __tablename__ = "price_bars"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(24), index=True, nullable=False)
    date = Column(String(10), nullable=False)              # YYYY-MM-DD (end-of-day)
    open = Column(Float); high = Column(Float); low = Column(Float)
    close = Column(Float); adj_close = Column(Float); volume = Column(Float)
    source = Column(String(16), nullable=False)            # demo | yfinance
    __table_args__ = (UniqueConstraint("ticker", "date", "source", name="uq_price"),)


class FetchMeta(Base):
    __tablename__ = "fetch_meta"
    key = Column(String(80), primary_key=True)
    fetched_at = Column(DateTime, default=utcnow)
    status = Column(String(16))
    message = Column(Text)


class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    uid = Column(String(40), unique=True, nullable=False)  # idempotency key
    ticker = Column(String(24), index=True, nullable=False)
    company_name = Column(String(160))
    headline = Column(Text, nullable=False)
    body_text = Column(Text)
    filed_at = Column(DateTime, index=True, nullable=False)
    exchange = Column(String(8))                           # NSE | BSE
    source = Column(String(8), nullable=False)             # demo | nse | bse
    url = Column(Text)
    attachment_url = Column(Text)
    category = Column(String(24), default="unclassified")
    category_confidence = Column(Float, default=0.0)
    classifier = Column(String(16), default="rules")       # rules | llm | rules+llm
    classifier_reasons = Column(JSON)
    priority = Column(String(10), default="low")           # critical | high | medium | low
    attention_score = Column(Integer, default=0)
    score_reasons = Column(JSON)
    summary_what = Column(Text); summary_why = Column(Text); summary_watch = Column(Text)
    summary_by = Column(String(24), default="rules")       # rules | ollama:<model>
    extracted = Column(JSON)                               # results table / management-change record
    is_demo = Column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    dedupe_key = Column(String(120), unique=True, nullable=False)
    ticker = Column(String(24), index=True)
    kind = Column(String(24))                              # price_move | volume_spike | announcement
    severity = Column(String(10), default="medium")
    title = Column(Text); detail = Column(Text)
    announcement_id = Column(Integer)
    created_at = Column(DateTime, default=utcnow)
    read = Column(Boolean, default=False)
    is_demo = Column(Boolean, default=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(24), index=True, nullable=False)
    doc_type = Column(String(24))                          # annual_report | concall
    title = Column(Text)
    period = Column(String(16))                            # FY26 | Q2FY27
    doc_date = Column(String(10))
    source_url = Column(Text)                              # original location (company / exchange / screener link)
    local_path = Column(Text)
    pages = Column(Integer, default=0)
    sha256 = Column(String(64), index=True)
    status = Column(String(16), default="ready")           # ready | failed
    is_demo = Column(Boolean, default=False)
    uploaded = Column(Boolean, default=False)
    fetched_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("ticker", "sha256", name="uq_doc"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ticker = Column(String(24), index=True)
    page = Column(Integer)
    idx = Column(Integer)
    text = Column(Text, nullable=False)
    embedding = Column(LargeBinary)                        # only populated for sentence-transformers


class Financial(Base):
    __tablename__ = "financials"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(24), index=True, nullable=False)
    period = Column(String(16), nullable=False)            # FY26 | Q2FY27
    period_type = Column(String(10), nullable=False)       # annual | quarterly
    period_end = Column(String(10))                        # YYYY-MM-DD for sorting
    metric = Column(String(24), nullable=False)
    value = Column(Float)
    unit = Column(String(16), default="INR_crore")
    source = Column(String(40))
    source_url = Column(Text)
    is_demo = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("ticker", "period", "metric", "is_demo", name="uq_fin"),)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(24), index=True)
    created_at = Column(DateTime, default=utcnow)
    payload = Column(JSON)
    generated_by = Column(String(40))
    is_demo = Column(Boolean, default=False)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(24), index=True)
    title = Column(String(120))
    created_at = Column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role = Column(String(10))
    content = Column(Text)
    citations = Column(JSON)
    meta = Column(JSON)
    created_at = Column(DateTime, default=utcnow)
