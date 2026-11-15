# FINN – Financial Investment Agent

A mobile-first prototype for the ENAM Holdings *AI Engineer Build Challenge*. FINN does two things for an investor:

* **Push** – a prioritised digest of what happened across a portfolio (exchange announcements, price and volume moves), with every priority score explained.
* **Pull** – an on-demand research report and a cited copilot for **any NSE ticker**, built *only* from the company's own annual reports and earnings-call transcripts.

> **Read this first – what is real and what is not.**
> The build sandbox could not reach Yahoo Finance, NSE, BSE or screener.in, so the live adapters are **written but not verified against the live sites**. To make the whole product demonstrable anyway, FINN ships a **labelled synthetic dataset** (18 companies, prices, filings, financials, and real PDFs with synthetic text). Everything synthetic is tagged **SAMPLE / DEMO** in the UI and can never appear in Live mode. See [Limitations](#limitations-and-what-is-unverified).

---

## Quick start (no API keys, no paid services)

Requirements: Python 3.11+, Node 18+.

```bash
./run.sh            # installs deps, builds the UI, serves everything on http://localhost:8000
```

Or step by step:

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
cd backend && ../backend/.venv/bin/uvicorn app.main:app --port 8000     # UI + API on :8000
```

Development with hot reload: `npm run dev:backend` and `npm run dev:frontend` (UI on :5173, proxied to :8000).

First start seeds the demo dataset automatically. Reload or reset it any time: *Settings → Load / reset demo data*, or `npm run seed`.

**Tests:** `npm test` (91 tests; isolated temp database, LLM disabled so results are deterministic).

### Optional: local LLM (free)
FINN is fully functional without one. To add a local model: install [Ollama](https://ollama.com), `ollama pull llama3.2:3b`, set `LLM_PROVIDER=ollama` in `backend/.env`. See [AI architecture](#ai-architecture) for exactly what the model is, and is not, allowed to do.

### Using Live mode
*Settings → Mode → Live*, then *Refresh live data* (prices via yfinance, announcements via NSE/BSE public endpoints). Research on any ticker then discovers annual reports and call transcripts via screener.in and ingests them. If a source blocks automated access, the UI shows the exact error and you can **upload the PDFs yourself** (Research → Add document); uploaded documents flow through the same pipeline.

---

## What you get

| Page | What it does |
|---|---|
| **Feed** | Digest for 24h / 3d / 7d / custom range. Critical → High → Medium sections, routine filings collapsed. Filters (category, priority, scope). "New since your last visit" strip. Alerts panel. Tap a filing: what / why / what to monitor, **attention-score reasons**, results table (Revenue, EBITDA, PBT, PAT with QoQ and YoY), management-change cards (person, role, effective date, quoted bio), original filing text. |
| **Portfolio** | 18 holdings with sparkline, EOD price, day move, volume vs 20-day average, news badges. Add any ticker (searchable directory or free-text NSE symbol), remove, sector exposure, portfolio snapshot (equal-weighted, stated as such). Price chart per holding. |
| **Research** | Enter any NSE ticker → job with live progress → report: business snapshot, financial snapshot, trajectory, balance sheet, cash quality, **narrative vs numbers** (promised vs delivered), guidance, bull vs bear, risks and accounting flags. Every section carries a confidence badge, a method note and citations that open **the source PDF at the cited page**. |
| **Copilot** | Chat per company with stored history. Answers carry numbered citations; tables for comparisons; refuses ("Insufficient evidence") rather than guessing. |
| **Settings** | Demo/Live, load demo, refresh live data, alert thresholds (price ±X%, volume multiple, categories, minimum priority, companies), LLM status, dark/light theme. |

Mobile (390 px) uses a bottom nav; desktop uses a sidebar. Loading, empty and error states exist on every page.

---

## Architecture

```
 React + Vite + Tailwind + Recharts          FastAPI                       SQLite (SQLAlchemy)
 ┌──────────────────────────┐   /api   ┌─────────────────────────┐      ┌───────────────────┐
 │ Feed  Portfolio Research │ ───────▶ │ routers                 │ ───▶ │ announcements     │
 │ Copilot  Settings        │          │  digest / portfolio /   │      │ price_bars        │
 └──────────────────────────┘          │  alerts / research /    │      │ financials        │
                                       │  copilot / system       │      │ documents, chunks │
   PUSH pipeline                       ├─────────────────────────┤      │ research_reports  │
   connector → classify → extract →    │ services                │      │ conversations …   │
   score → summarise → alert           │  (all deterministic     │      └───────────────────┘
                                       │   core + optional LLM)  │
   PULL pipeline                       └─────────────────────────┘
   discover → download → PDF text → chunk → index → calculate → report → copilot
```

**Push pipeline** (`backend/app/services`)
1. *Connectors* (`announcement_ingestion.py`): `NSEConnector`, `BSEConnector`, `DemoConnector` share one interface – swap or add a feed without touching anything else. Idempotent by content hash.
2. *Classifier* (`announcement_classifier.py`): 17 categories from the brief. Weighted regex rules with suppressors (e.g. ESOP allotments are not fund raises; promoter trades are not management changes; auditor appointments are not management changes); headline weighs more than body. A local LLM is consulted only when rule confidence is low, and its answer must be a valid taxonomy label.
3. *Extractors* (`announcement_extractors.py`): results tables (Indian number formats, negatives, unit detection, **column order verified against period headers**, consolidated preferred, EBITDA derived as PBT + finance cost + depreciation − other income and **flagged "derived"**, banks reported as "not found" instead of invented). Management changes are extracted per person with role, effective date, previous role and a bio **quoted from the filing** – never scraped or invented; a manual web-search link is offered instead.
4. *Priority engine* (`prioritisation.py`): base weight per category + named modifiers (senior role, rating downgrade, amount relative to company size, results swing, severe wording, portfolio relevance); routine filings are capped. Bands: critical ≥ 80, high ≥ 55, medium ≥ 30. **Every point is listed in the UI.**
5. *Alerts* (`alert_engine.py`): price ±X%, volume ≥ N× 20-day average, categories, minimum priority, companies. Deduplicated; re-evaluated when settings change.

**Pull pipeline**
1. *Discovery* (`company_discovery.py`): resolve ticker → screener.in → structured financials plus annual-report and concall-transcript links; PDFs downloaded (size-capped, `%PDF` verified).
2. *Ingestion* (`pdf_extraction.py`, `document_ingestion.py`): PyMuPDF text per page; page-aware chunks; scanned/empty PDFs are **reported as failed, not faked**; idempotent.
3. *Retrieval* (`retrieval.py`): per-company TF-IDF (1–2-grams) with a relevance gate; optional sentence-transformers.
4. *Calculations* (`financial_calculations.py`): pure functions – growth, margins, D/E, ROE (average equity), ROCE, CFO/PAT, FCF, CAGR, volume deviation – with a published methodology. Growth against a non-positive base is "n.m.", never a fake percentage.
5. *Guidance* (`guidance.py`): a statement counts as explicit guidance only with a forward-looking marker **and** a number for a recognised metric; qualitative commentary stays qualitative. Delivered/missed/tracking/pending/not-verifiable assessments use stated tolerances.
6. *Report* (`research_agent.py`) and *Copilot* (`copilot.py`): see below.

---

## AI architecture

**Principle: numbers and claims come from code and documents; a language model may only rephrase.**

| Task | Method | LLM role |
|---|---|---|
| Classification | Rules + suppressors | Optional tie-break for low confidence; output validated against the taxonomy |
| Results / management extraction | Deterministic parsers | None |
| Scores and summaries | Explainable weights; templated what/why/watch | Optional rewrite, **rejected if it introduces any number not in the source** |
| Financial maths | Pure Python | None |
| Guidance and promised-vs-delivered | Regex + deterministic assessment | None |
| Report sections | Structured data + retrieved passages | Only the business paragraph; numeric-validated |
| Copilot | Intent → handler over structured data + TF-IDF passages, numbered citations, relevance gate | Optional rewrite; **rejected unless every citation index exists and every number is in the cited sources** |

Consequences: it runs free on a laptop; behaviour is reproducible and testable; an unsupported question gets *"Insufficient evidence"* rather than a plausible guess; no model memory, broker report or news is used on the pull side.

Follow-up questions inherit the previous topic only when they are real follow-ups ("and last year?", "explain that"), never for fresh unrelated questions (a bug caught and fixed during browser testing; covered by a regression test).

---

## Data sources and cost

| Need | Source | Cost |
|---|---|---|
| Prices, volume | yfinance (`.NS`, then `.BO`), end-of-day, 30-minute cache | free |
| Announcements | NSE / BSE public JSON endpoints | free |
| Financials, filing links | screener.in public pages | free |
| Documents | Annual reports and transcripts from those links, or user upload | free |
| Retrieval | scikit-learn TF-IDF (local) | free |
| LLM | none required; optional Ollama (local) | free |

Cost optimisation is structural: deterministic extraction means **zero per-request model cost**; prices are cached; documents are chunked and indexed once and reused; research reports are cached per company and mode; live refresh is an explicit action (or a configurable background interval).

---

## Design trade-offs

* **Deterministic first, LLM optional.** Less fluent prose, far fewer ways to be wrong. Accuracy and auditability were prioritised over polish.
* **TF-IDF instead of embeddings by default.** Works offline with no model download; weaker on paraphrase. Swappable via `EMBEDDINGS_PROVIDER`.
* **Regex guidance extraction.** Precise but conservative: it will miss unusually phrased guidance rather than invent a target.
* **Equal-weighted portfolio.** Position sizes are not collected, so exposure is shown equal-weighted and labelled so.
* **SQLite + in-process background jobs.** Right for a single-user prototype; a queue and Postgres are the production step.

## Limitations and what is unverified

Be sceptical of anything in this list.

* **Live adapters not exercised live.** yfinance, NSE, BSE and screener.in were blocked in the build sandbox (the app shows these exact errors in Live mode). The adapters follow the public endpoint shapes and the screener *parser* is unit-tested against an HTML fixture, but **real-site behaviour (anti-bot, layout changes, rate limits) is untested**. Expect to tune headers/cadence.
* **Demo data is synthetic.** Prices, filings, financials and PDFs are generated. Planted events (e.g. a volume spike, a CFO change) exist to exercise the pipeline. They are not real companies' results.
* **Ticker `TMPV`** (Tata Motors passenger vehicles after the demerger) in the directory should be verified against current NSE symbols.
* **Optional paths untested:** Ollama refinement and sentence-transformers embeddings. Tests run with the LLM disabled; the LLM-verification logic is tested with a fake provider only.
* **PDF quality:** scanned (image-only) reports are detected and reported, but no OCR is performed.
* **Guidance/risk extraction is heuristic.** Real transcripts are messier than the synthetic ones; confidence badges and "not verifiable" statuses exist to say so.
* **Not investment advice.** Outputs are analytical summaries of public documents.

## Next steps
Run the live adapters against real feeds and harden them; OCR for scanned reports; position-size tracking; semantic retrieval by default with a cross-encoder reranker; a job queue and Postgres; authentication; push notifications; evaluation set of real filings for classifier and extractor accuracy.

## Repository layout
```
backend/   FastAPI app (app/), tests (tests/), seed script (scripts/), requirements.txt, .env.example
frontend/  React + Vite + Tailwind app (src/), package.json
run.sh     one-command local run          COVERING_NOTE.md   draft note for ENAM
BUILD_HISTORY.md   what AI conversations/build history to preserve for submission
```
