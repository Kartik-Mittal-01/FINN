# Build history to preserve for submission

The challenge asks for the AI conversations used to build the project. **Only genuine records should be submitted; nothing here is fabricated or reconstructed.** This file lists what exists and how to keep it.

## What exists
1. **The master build prompt** – the instruction document that started the build (the attached `attachment.txt`: "MASTER BUILD PROMPT — FINN: Financial Investment Agent"). Include it verbatim.
2. **The full Claude Code build session** – one long agentic session in which the whole repository (backend, tests, frontend, docs) was written, run, debugged and verified. Its raw transcript is stored in the build container at
   `/root/.claude/projects/-home-claude/dac817d0-ff0a-5126-95a1-d1180e26d9b3.jsonl`.
   The session ran past the context limit once and was continued from an automatic summary; the transcript file contains the complete text including the part before that point.
3. The two ENAM documents supplied as inputs (the challenge brief PDF and the announcement-categories / glossary reference PDF).

## Action needed from you
The build container is ephemeral. **Before it is reclaimed, export the transcript** (download the `.jsonl` above, or use the app's export/share for the conversation) and attach it with the master prompt. If you also used any *other* AI chat to plan or review this work, add those transcripts too – I only know about the one above, and I will not list conversations I cannot see.

## Notable build events worth pointing reviewers to
(These are real; each is visible in the transcript.)
- Environment discovery: live exchange / Yahoo / screener hosts were blocked, which led to the demo-mode + connector-interface design.
- Classifier fixes found by tests: body-only evidence, bond-vs-fund-raise confusion, ESOP/promoter-trade/auditor suppressors.
- Management-change extractor rewritten to be per-person after multi-person filings produced merged output.
- Unrealistic bank ROE and double-counted guidance revisions caught by review and fixed.
- Guidance fiscal-year attribution bug (a merged header "Q4 FY25 earnings call" caused FY26 guidance to be filed under FY25), found by the unseen-ticker test and fixed by anchoring to the nearest FY mention.
- Copilot bug found in browser testing: an unrelated question ("capital of France?") inherited the previous topic and returned a confident answer; fixed with an explicit follow-up rule and a regression test.
- Mobile layout bugs found in screenshots (grid overflow, overlapping sparkline, composer hidden by the bottom nav) and fixed.
