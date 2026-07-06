---
type: decision
title: "Decision log"
status: implemented
tags: [decisions, cadquery, gemma, process]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
  - "mech-eng repo (hackathon original) commit history"
---

# Decision log

Append new decisions at the bottom with the next D-number. Reversals get a new
entry referencing the old one, not an edit.

## D-001 — Keep parametric code-CAD (CadQuery); reject mesh text-to-3D

**Decision:** Module 1 generates **CadQuery Python** that is executed into a
parametric B-rep solid (STEP/STL). Mesh-based text-to-3D generators are rejected.

**Why:** meshes are not physics-valid for mechanical engineering — no exact
geometry, no reliable watertight solids, no parametric dimensions to check
against the request, and FEA in [[module-2-simulation]] needs sound B-rep
geometry. Code-CAD also gives free auditability (the design *is* source code)
and a natural self-correction loop (execution errors are feedback). The
hackathon repo validated this approach (its ADR-009, "Generative CAD").

## D-002 — Gemma on vLLM / AMD MI300X is the primary LLM path

**Decision:** the design and analysis LLM is Gemma served by vLLM on an AMD
MI300X droplet (OpenAI-compatible endpoint); the provider layer stays
provider-agnostic with Fireworks/OpenRouter as explicit fallbacks.

**Why:** the Gemma-on-AMD path is the sponsor-critical differentiator and prize
target of the hackathon track; losing it in a refactor would defeat the
project's purpose. Details in [[infra-gemma-vllm-amd]].

## D-003 — Rebuild module by module, tested in isolation

**Decision:** each module ([[module-1-design]] → [[module-2-simulation]] →
[[module-3-analysis]]) is built, run, and tested standalone (file I/O + shared
schemas) before the next starts; the orchestrator comes last.

**Why:** the hackathon original grew entangled under time pressure; the rebuild
exists to get clean seams. Isolation is what makes each module independently
testable and the failures attributable.

## D-004 — Errors surface; fallbacks are never silent

**Decision:** every HTTP/LLM/solver failure is reported with its real cause
(status, content-type, body/log snippet). Any fallback (provider, template,
skipped check) must announce itself and why.

**Why:** the safebrowse.io interception ([[infra-gemma-vllm-amd]]) cost real
debugging time precisely because a silent path hid the true failure; the old
repo's final commits were about undoing that damage. Cheaper to never regress.

## D-005 — LLM-maintained wiki with human-confirmed commits

**Decision:** project knowledge lives in this wiki (conventions in
`wiki/SCHEMA.md`), updated by the `wiki-maintainer` skill via `/wiki-update`
(manual, primary) or an **opt-in, disabled-by-default** post-commit hook. The
skill never auto-commits.

**Why:** docs that lag code are worse than none, but per-commit headless LLM
runs cost tokens and need trust built first — hence manual-first with diffs
reviewed by a human, and a one-line opt-in for automation later.

Links: [[architecture]]
