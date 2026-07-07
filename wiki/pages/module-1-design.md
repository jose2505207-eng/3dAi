---
type: module
title: "Module 1 — Design: text → Gemma → CadQuery → STEP/STL"
status: implemented
tags: [design, gemma, cadquery, llm, self-correction]
updated: 2026-07-07
sources:
  - "project brief (2026-07-06)"
  - "modules/design/loop.py:88"
  - "modules/design/sandbox.py:87"
  - "modules/design/runner.py:53"
  - "modules/design/prompts.py:13"
  - "modules/design/__main__.py:31"
  - "modules/design/tests/test_live.py:26"
  - "outputs/design/20260707-172325-*/sim_report.json (holeless 2-solid bracket)"
---

# Module 1 — Design

**Status: working** (schema enum: `implemented`). Runs and passes its tests in
full isolation — file-based CLI, no orchestrator. 17 offline tests + 1 live
smoke test (`.venv/bin/pytest modules/design/tests/`).

## Behavior (as built)

Input: a natural-language part description. Output: `part.step`, `part.stl`,
`part.py` (the final parametric CadQuery script), and `run_record.json`, all
under one output dir. Entry points: `run_design()` (modules/design/loop.py:88)
and the CLI `python -m modules.design "<prompt>"` (modules/design/__main__.py:31),
default output `outputs/design/<stamp>-<slug>/` (modules/design/__main__.py:25).

Pipeline per iteration (budget `CAD_MAX_ITERATIONS`, default 5 —
modules/design/loop.py:32):

1. **Preflight (before any LLM call):** `GET $VLLM_BASE_URL/models` must
   answer JSON, or the run refuses to start with the real evidence recorded
   (modules/design/loop.py:116, shared/llm.py:144) — see
   [[infra-gemma-vllm-amd]].
2. **Generate:** Gemma (via `shared/llm.py`, the provider layer) writes a
   CadQuery script; system prompt at modules/design/prompts.py:13. The prompt
   demands a SINGLE FUSED SOLID (modules/design/prompts.py:21) and that any
   parameterized holes are physically cut with `.hole()`/`cutThruAll()`
   (modules/design/prompts.py:24).
3. **AST safety validation:** import whitelist {cadquery, math, numpy},
   forbidden builtins, no dunder access (modules/design/sandbox.py:25,87).
4. **Sandboxed build:** separate `python -I` subprocess, hard timeout,
   scratch cwd (modules/design/sandbox.py:129).
5. **Geometry validation:** exactly ONE solid (`< 1` and `> 1` both fail —
   modules/design/sandbox.py:152,154), volume > 0, OCCT `isValid()`,
   watertight — every shell closed — and **declared holes must exist**: if
   the script's parameters name a hole/bore but the solid has zero
   cylindrical faces, the gate fails and tells Gemma to cut them
   (modules/design/sandbox.py:166; face census in
   modules/design/runner.py:53). STEP **and** STL must export.
6. **Self-correction:** any safety/execution/validation failure feeds the
   *real* error text (violations, traceback tail, failing metrics) back to
   Gemma via a retry prompt containing the previous script
   (modules/design/prompts.py:50).

An **LLM-call failure is never retried inside the loop** — it aborts
immediately with the real HTTP evidence (modules/design/loop.py:137), per the
no-silent-fallback doctrine. Exit codes: 0 success, 1 budget exhausted,
2 config/endpoint failure (modules/design/__main__.py:62).

## Run record (provenance)

`run_record.json` lists every iteration with the `CallRecord` of the actual
HTTP round-trip — endpoint, model, HTTP status, vLLM response id, token
counts, latency (shared/llm.py:43, modules/design/loop.py:47) — so a
template/stub answer can never masquerade as a real Gemma run. It also
captures the preflight result and the part's parameters (top-level numeric
assignments extracted from the final script — `extract_parameters` now lives
in modules/design/sandbox.py:61, where the hole gate also uses it;
modules/design/loop.py:156 records it).

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
  only (modules/design/prompts.py:31, lesson carried over from the hackathon
  repo).
- **Disconnected unions** produce non-watertight solids — the prompt requires
  every `union()` operand to physically overlap its neighbour.
- **Multi-body "brackets" and phantom holes** (observed 2026-07-07): a live
  bracket run shipped 2 disconnected solids with a `hole_diameter` parameter
  but zero cylindrical faces; [[module-2-simulation]] failed it downstream
  (`single_body`, `hole_geometry`) and could not anchor FEA boundary
  conditions (no holes to fix). Fix is both prompt and gate: the prompt now
  demands one fused solid and physically cut holes
  (modules/design/prompts.py:21,24), and geometry validation fails
  `solid_count > 1` (modules/design/sandbox.py:154) and
  declared-holes-with-zero-cylindrical-faces (modules/design/sandbox.py:166),
  feeding both back into the retry loop. Verified live: the re-run bracket
  passes `single_body` and `hole_geometry` in Module 2.
- (Append new patterns observed in live runs here, with the prompt fix.)

## Testing

- Offline (no network): AST validator accept/reject, real sandboxed build of
  a known-good part, traceback-feedback surfacing, and the two hardening
  gates — disconnected 2-solid union rejected
  (modules/design/tests/test_sandbox.py:49), declared-but-uncut hole
  rejected naming the offending parameter
  (modules/design/tests/test_sandbox.py:61); loop convergence, budget
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
