"""Evidence retrieval over a company's ingested documents.

Default: TF-IDF (1-2 grams, sublinear tf) fitted on the company's chunks – tiny, fast, no model download.
Optional: sentence-transformers vectors (stored at ingestion). Either way the contract is the same: return ranked
chunks with scores and document metadata, or *nothing* when nothing is relevant (the caller then says 'insufficient
evidence' rather than letting a model improvise)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy.orm import Session

from ..models import Chunk, Document
from . import embeddings
from .document_ingestion import view_url

MIN_SCORE = 0.10
_cache: dict = {}
BANNER_PREFIX = "SAMPLE DOCUMENT - synthetic"


def strip_boilerplate(text: str) -> str:
    """Drop the demo-document banner line (kept in the stored chunk for fidelity, hidden from excerpts)."""
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith(BANNER_PREFIX))


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    score: float
    page: int
    text: str
    doc_title: str
    doc_type: str
    period: Optional[str]
    source_url: Optional[str]
    view_url: str
    is_demo: bool

    def citation(self, n: Optional[int] = None) -> dict:
        excerpt = re.sub(r"\s+", " ", strip_boilerplate(self.text)).strip()
        return {"n": n, "doc_id": self.doc_id, "title": self.doc_title, "doc_type": self.doc_type, "period": self.period,
                "page": self.page, "excerpt": excerpt[:420] + ("…" if len(excerpt) > 420 else ""),
                "url": self.view_url, "source_url": self.source_url, "is_demo": self.is_demo, "score": round(self.score, 3)}


SENT_SPLIT = re.compile(r"(?<=[.!?])(?<!Rs\.)(?<!Mr\.)(?<!Ms\.)(?<!No\.)(?<!Dr\.)(?<!Ltd\.)\s+(?=[A-Z\"'])")


def split_sentences(text: str) -> list[str]:
    return [x.strip() for x in SENT_SPLIT.split(re.sub(r"\s+", " ", text)) if x.strip()]


def query_terms(q: str) -> set[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as SW
    return {w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in SW}


def _load(db: Session, ticker: str, is_demo: bool, doc_types):
    q = (db.query(Chunk, Document).join(Document, Chunk.doc_id == Document.id)
         .filter(Chunk.ticker == ticker, Document.is_demo == is_demo, Document.status == "ready"))
    if doc_types:
        q = q.filter(Document.doc_type.in_(doc_types))
    return q.order_by(Chunk.id).all()


def search(db: Session, ticker: str, query: str, *, k: int = 6, is_demo: bool = False, doc_types=None,
           periods=None, min_score: float = MIN_SCORE) -> list[Hit]:
    rows = _load(db, ticker, is_demo, doc_types)
    if periods:
        rows = [r for r in rows if r[1].period in periods]
    if not rows or not query.strip():
        return []
    texts = [c.text for c, _ in rows]
    scores = None
    if embeddings.provider_name() == "sentence-transformers" and all(c.embedding for c, _ in rows):
        qv = embeddings.embed([query])
        mat = np.vstack([np.frombuffer(c.embedding, dtype="float32") for c, _ in rows])
        scores = mat @ qv[0]
        min_score = max(min_score, 0.25)
    else:
        key = (ticker, is_demo, tuple(doc_types or ()), tuple(periods or ()), len(rows), rows[-1][0].id)
        if key not in _cache:
            vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
            _cache.clear() if len(_cache) > 40 else None
            _cache[key] = (vec, vec.fit_transform(texts))
        vec, mat = _cache[key]
        scores = (mat @ vec.transform([query]).T).toarray().ravel()
    # Long chunks dilute cosine for short queries, so also accept chunks that contain most of the query's content words.
    terms = query_terms(query)
    cov = np.array([sum(1 for w in terms if w in t.lower()) / len(terms) for t in texts]) if terms else np.zeros(len(texts))
    ranked = scores + 0.15 * cov
    order = np.argsort(-ranked)[:k * 2]
    hits = []
    for i in order:
        if len(hits) >= k:
            break
        if scores[i] < min_score and not (cov[i] >= 0.6 and scores[i] >= 0.03):
            continue
        c, d = rows[i]
        hits.append(Hit(c.id, d.id, float(scores[i]), c.page, c.text, d.title, d.doc_type, d.period, d.source_url,
                        view_url(d, c.page), d.is_demo))
    return hits


def all_chunks(db: Session, ticker: str, is_demo: bool, doc_types=None):
    """Every chunk (ordered) with its document – used by deterministic extractors (guidance, segment mix)."""
    return _load(db, ticker, is_demo, doc_types)
