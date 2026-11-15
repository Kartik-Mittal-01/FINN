# Covering note – FINN (DRAFT for review before sending)

**To:** ENAM Holdings – AI Engineer Build Challenge, IIT Delhi 2027
**From:** [Your name, programme, email]
**Re:** FINN – Financial Investment Agent (submission)

Dear Team,

Please find attached FINN, a working, mobile-first prototype of the investment agent described in the brief. Repository: [link]. It runs locally with one command (`./run.sh`), needs no API keys, and has 91 automated tests.

## What I built
FINN has the two modes the brief asks for.
**Push:** a prioritised digest over an 18-company portfolio for 24h / 3d / 7d / custom windows. Announcements are classified into the 17 categories in the reference sheet, scored Critical/High/Medium/Low with every contributing factor shown, and enriched with a results table (Revenue, EBITDA, PBT, PAT with QoQ/YoY) or per-person management-change cards. Price and volume alerts are configurable (±X%, multiple of the 20-day average, categories, minimum priority, companies).
**Pull:** research on any NSE ticker from primary documents only – business, financials, trajectory, balance sheet, cash quality, *narrative vs numbers*, guidance, bull vs bear, risks – each section with a confidence badge and citations that open the source PDF at the cited page, plus a conversational copilot that cites or declines.

## Philosophy
An investor's worst outcome from an AI tool is a confident, plausible, wrong number. So the numbers and claims come from deterministic code and quoted documents; a language model is optional and may only rephrase, and its output is rejected if it adds a figure or citation not present in the sources. When the evidence is missing the product says "Insufficient evidence", "not verifiable" or "not found" instead of filling the gap.

## Architecture and AI/retrieval strategy
React/Vite/Tailwind front end; FastAPI + SQLite back end. Push: connector → hybrid rules classifier (with suppressors for look-alike filings) → extractors (column order verified against period headers) → explainable priority engine → alerts. Pull: discovery → PDF text → page-aware chunks → per-company TF-IDF retrieval (sentence-transformers optional) → deterministic calculation module → report and copilot. Full detail, including the per-task role of the LLM, is in the README.

## Data sources and cost
yfinance (end-of-day, cached), NSE/BSE public announcement endpoints, screener.in for financials and document links, user upload as fallback. Everything is free. Because extraction and calculation are deterministic, per-request model cost is zero; documents are indexed once and reports are cached.

## Trade-offs
Deterministic-first favours accuracy and auditability over fluent prose. TF-IDF retrieval is weaker on paraphrase than embeddings. Guidance extraction is conservative and will miss unusual phrasing rather than invent a target. Portfolio exposure is equal-weighted because position sizes are not collected.

## What I did not do, and what is not verified
I want to be direct about this:
- **The live data adapters (yfinance, NSE, BSE, screener.in) were written but could not be exercised against the real sites** from my build environment, which blocked them. The screener parser is unit-tested on an HTML fixture only. Expect some tuning on first live run.
- To demonstrate the whole pipeline regardless, the app includes a **clearly labelled synthetic demo dataset**. All prices, filings, financials and documents in Demo mode are generated and are marked SAMPLE; they are not real results and the app never mixes them into Live mode.
- Ollama and semantic-embedding paths are implemented but untested; the test suite runs with the LLM disabled.
- No OCR for scanned PDFs (they are detected and reported). One ticker (TMPV) should be verified against current NSE symbols.

## Next steps
Validate and harden the live adapters; evaluate classifier/extractor accuracy on a labelled set of real filings; OCR; position-size tracking; semantic retrieval with reranking; job queue and Postgres; authentication and push notifications.

I have attached my build history (AI conversations) as requested. Thank you for the opportunity.

Regards,
[Name]
