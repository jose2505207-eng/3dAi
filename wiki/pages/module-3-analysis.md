---
type: module
title: "Module 3 — Analysis: Gemma writes the technical summary"
status: planned
tags: [analysis, gemma, llm, reporting]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
---

# Module 3 — Analysis

**Status: planned.** Built after [[module-2-simulation]]. Detailed spec deferred;
this records the agreed shape.

## Spec (outline)

Input: the simulation report (deterministic checks + FEA results) and the
original design request/metadata. Output: a human-readable **technical summary**
written by Gemma: does the part meet the request, where are the stress hotspots,
what are the margins, what should change.

- Uses the same provider layer as Module 1 ([[infra-gemma-vllm-amd]]) — Gemma on
  vLLM/AMD is the primary path here too.
- Grounding rule: every quantitative claim in the summary must come from the
  simulation report it was given — the prompt/validation design must make
  fabricated numbers detectable.
- Same error-surfacing rule as everywhere: endpoint failures are reported, not
  papered over.

## Isolation test plan (sketch)

Feed canned simulation reports (fixtures) and assert the summary is produced,
cites only numbers present in the fixture, and flags failing checks.

Links: [[architecture]] · [[module-2-simulation]] · [[module-1-design]]
