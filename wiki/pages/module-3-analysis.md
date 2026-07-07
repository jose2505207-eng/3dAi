---
type: module
title: "Module 3 — Analysis: Gemma writes the technical summary"
status: implemented
tags: [analysis, gemma, llm, reporting, grounding]
updated: 2026-07-07
sources:
  - "project brief (2026-07-06)"
  - "modules/analysis/analyze.py:91"
  - "modules/analysis/grounding.py:53"
  - "modules/analysis/prompts.py:13"
  - "modules/analysis/__main__.py:24"
  - "modules/analysis/tests/conftest.py"
---

# Module 3 — Analysis

**Status: working** (schema enum: `implemented`). Runs and passes its tests in
full isolation. 16 offline tests + 1 live smoke test
(`.venv/bin/pytest modules/analysis/tests/`).

## Behavior (as built)

Input: a run dir containing **both** `run_record.json` (Module 1) and
`sim_report.json` (Module 2, schema `sim_report/v1`) — a half-run dir is
refused with `AnalysisInputError`, never summarized
(modules/analysis/analyze.py:63). Output, into the same run dir:
`analysis.md` (the human-readable technical summary) and
`analysis_record.json` (provenance).

Entry points: `run_analysis(run_dir, client, *, temperature=0.3,
strict=False)` (modules/analysis/analyze.py:91 — the API the orchestrator
imports) and the CLI `python -m modules.analysis <run-dir> [--strict]`
(modules/analysis/__main__.py:24). CLI exit codes: 0 summary written;
1 `--strict` and grounding flagged a number; 2 config/endpoint/LLM failure
or missing/invalid inputs — inputs are validated *before* the client is
created (modules/analysis/__main__.py:39), so a half-run dir is refused
regardless of endpoint availability.

Uses the same provider layer as Module 1 ([[infra-gemma-vllm-amd]]):
`preflight()` before the first call, then one `chat()`. On `LLMError` the
real evidence is surfaced and the failure record is still written for audit
— no silent fallback, no stub summary.

## Prompt contract

The model receives the FULL `sim_report.json` plus the run_record's
prompt/parameters as ground truth (modules/analysis/prompts.py:44) and must
cover: verdict vs the request, every check with real values (`not_run`
reported WITH its recorded reason), FEA with the assumed boundary conditions
quoted **verbatim** (they are heuristics a reader must judge), margins, and
concrete recommendations (modules/analysis/prompts.py:13).

## Numeric grounding (the honesty core — and its limits)

An allow-set of numeric magnitudes is built from the inputs
(modules/analysis/grounding.py:53); after generation, numeric tokens in
`analysis.md` with no ~1 %-tolerant match are recorded in
`grounding.flagged` (modules/analysis/grounding.py:69, tolerance at :24).
This is a **heuristic that surfaces suspect numbers, not a proof of
correctness**: it false-positives on correctly-derived arithmetic (the first
live run flagged `470.4 − 200 = 270.4` and `276 / 2 = 138` — both right) and
can false-negative on a fabrication that coincides with an input number. By
default it warns (stderr + record); only `--strict` fails the run. The
record says so itself (modules/analysis/analyze.py:26).

Token extraction lesson: the first regex silently skipped numbers at the end
of a sentence ("…of 9.7." — the trailing period tripped the lookahead); the
offline fabricated-number test caught it (modules/analysis/grounding.py:20).

## Testing

- Offline (fake client, no network): passing + failing fixture run dirs
  (modules/analysis/tests/conftest.py); summary + record written and
  validated; fabricated number flagged / clean output unflagged; missing
  either input → exit 2; `--strict` exit codes; LLM and preflight failures
  surface with the record on disk (modules/analysis/tests/test_analysis.py,
  test_grounding.py).
- Live: real endpoint, provenance asserted (response id, HTTP 200), skips
  gracefully when `VLLM_BASE_URL` is unset
  (modules/analysis/tests/test_live.py).

Links: [[architecture]] · [[module-2-simulation]] · [[module-1-design]] ·
[[infra-gemma-vllm-amd]]
