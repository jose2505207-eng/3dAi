---
type: module
title: "Module 1 — Design: text → Gemma → CadQuery → STEP/STL"
status: planned
tags: [design, gemma, cadquery, llm, self-correction]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
---

# Module 1 — Design

**Status: planned.** First module to be built; must run and pass tests in full
isolation (file-based CLI, no orchestrator) before Module 2 starts.

## Spec

Input: a natural-language part description (e.g. "an L-bracket, 5 mm thick, two
M6 holes"). Output: a valid **parametric** solid as STEP + STL, plus the CadQuery
source that produced it and a machine-readable result record.

Pipeline:

1. Prompt Gemma (via the provider layer in [[infra-gemma-vllm-amd]]) to write
   **CadQuery Python** for the requested part.
2. Execute the generated code in a sandboxed subprocess.
3. Validate the result: code ran, produced a solid, solid is a valid closed
   B-rep, exports to STEP/STL succeed.
4. **Self-correction loop:** on any failure, feed the real error (traceback,
   validation message) back to Gemma and regenerate, up to a bounded number of
   iterations. Every iteration is recorded (the old repo kept a provenance
   ledger of iterations — keep that idea).

## Hard constraints

- **Parametric code-CAD (CadQuery) only.** Mesh text-to-3D is explicitly
  rejected: meshes aren't physics-valid B-rep solids, so downstream FEA in
  [[module-2-simulation]] would be meaningless. Rationale in [[decisions]].
- **Surface real errors.** If the LLM endpoint fails (HTTP error, HTML instead
  of JSON, timeout), the module reports that exact failure. No silent fallback
  to another provider or to a template — the safebrowse.io incident
  ([[infra-gemma-vllm-amd]]) and the old repo's "surface the real reason when
  generative mode falls back to template" fix are why this is a hard rule.
- Generated code runs sandboxed (subprocess, timeout, no network).

## Isolation test plan (definition of done)

- Unit tests for prompt construction, sandbox execution, validation, and the
  correction loop (with a mocked LLM).
- One live smoke test against the real Gemma/vLLM endpoint.
- CLI: `text in → .step/.stl out` on a handful of benchmark prompts.

Links: [[architecture]] · [[infra-gemma-vllm-amd]] · [[decisions]]
