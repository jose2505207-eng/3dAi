---
type: module
title: "Module 1 — Design: text → Gemma → CadQuery → STEP/STL"
status: implemented
tags: [design, gemma, cadquery, llm, self-correction]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
  - "modules/design/loop.py:108"
  - "modules/design/sandbox.py:56"
  - "modules/design/runner.py:48"
  - "modules/design/prompts.py:13"
  - "modules/design/__main__.py:31"
  - "modules/design/tests/test_live.py:26"
---

# Module 1 — Design

**Status: working** (schema enum: `implemented`). Runs and passes its tests in
full isolation — file-based CLI, no orchestrator. 15 offline tests + 1 live
smoke test (`.venv/bin/pytest modules/design/tests/`).

## Behavior (as built)

Input: a natural-language part description. Output: `part.step`, `part.stl`,
`part.py` (the final parametric CadQuery script), and `run_record.json`, all
under one output dir. Entry points: `run_design()` (modules/design/loop.py:108)
and the CLI `python -m modules.design "<prompt>"` (modules/design/__main__.py:31),
default output `outputs/design/<stamp>-<slug>/` (modules/design/__main__.py:25).

Pipeline per iteration (budget `CAD_MAX_ITERATIONS`, default 5 —
modules/design/loop.py:32):

1. **Preflight (before any LLM call):** `GET $VLLM_BASE_URL/models` must
   answer JSON, or the run refuses to start with the real evidence recorded
   (modules/design/loop.py:136, shared/llm.py:144) — see
   [[infra-gemma-vllm-amd]].
2. **Generate:** Gemma (via `shared/llm.py`, the provider layer) writes a
   CadQuery script; system prompt at modules/design/prompts.py:13.
3. **AST safety validation:** import whitelist {cadquery, math, numpy},
   forbidden builtins, no dunder access (modules/design/sandbox.py:25,56).
4. **Sandboxed build:** separate `python -I` subprocess, hard timeout,
   scratch cwd (modules/design/sandbox.py:98).
5. **Geometry validation:** ≥1 solid, volume > 0, OCCT `isValid()`, and
   watertight — every shell closed (modules/design/runner.py:48; judged at
   modules/design/sandbox.py:122-128). STEP **and** STL must export.
6. **Self-correction:** any safety/execution/validation failure feeds the
   *real* error text (violations, traceback tail, failing metrics) back to
   Gemma via a retry prompt containing the previous script
   (modules/design/prompts.py:44).

An **LLM-call failure is never retried inside the loop** — it aborts
immediately with the real HTTP evidence (modules/design/loop.py:157), per the
no-silent-fallback doctrine. Exit codes: 0 success, 1 budget exhausted,
2 config/endpoint failure (modules/design/__main__.py:62).

## Run record (provenance)

`run_record.json` lists every iteration with the `CallRecord` of the actual
HTTP round-trip — endpoint, model, HTTP status, vLLM response id, token
counts, latency (shared/llm.py:43, modules/design/loop.py:59) — so a
template/stub answer can never masquerade as a real Gemma run. It also
captures the preflight result and the part's parameters (top-level numeric
assignments extracted from the final script, modules/design/loop.py:84).

## Hard constraints (unchanged)

- **Parametric code-CAD (CadQuery) only** — rationale in [[decisions]].
- **Surface real errors** — the safebrowse.io incident
  ([[infra-gemma-vllm-amd]]) is why; HTML responses are labeled as probable
  proxy/filter interception (shared/llm.py:28).
- Generated code runs sandboxed (subprocess, timeout, no network).

## Known Gemma/CadQuery failure patterns → prompt fixes

- **OCCT-fragile operations** (`fillet()`, `chamfer()`, `shell()` on unioned
  solids, `loft()`, `sweep()`) fail constantly on generated geometry — the
  system prompt forbids them outright; boxes/cylinders/extrudes/cuts/unions
  only (modules/design/prompts.py:25, lesson carried over from the hackathon
  repo).
- **Disconnected unions** produce non-watertight solids — the prompt requires
  every `union()` operand to physically overlap its neighbour.
- (Append new patterns observed in live runs here, with the prompt fix.)

## Testing

- Offline (no network): AST validator accept/reject, real sandboxed build of
  a known-good part, traceback-feedback surfacing
  (modules/design/tests/test_sandbox.py); loop convergence, budget
  exhaustion, LLM-failure abort, preflight refusal, provenance fields, with a
  fake client (modules/design/tests/test_loop.py).
- Live: full loop against the real endpoint, asserts a valid manifold STEP
  re-imports and that every iteration shows a real Gemma call; skips
  gracefully when `VLLM_BASE_URL` is unset
  (modules/design/tests/test_live.py:18,26).
- Manual verification (must run from a network path that reaches the
  droplet): watch `docker logs -f gemma` for `POST /v1/chat/completions 200`
  — steps in README.md ("Manual verification").

Links: [[architecture]] · [[infra-gemma-vllm-amd]] · [[decisions]]
