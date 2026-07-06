---
type: architecture
title: "System architecture: prompt → design → simulation → analysis"
status: planned
tags: [architecture, pipeline, modules, orchestrator]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
---

# System architecture

Natural-language prompt in, engineered part + technical report out. Three
independent modules plus an orchestrator, rebuilt from the hackathon repo
**module by module** — each module runs and is tested in full isolation before
the next is started. Nothing here is implemented yet; this page records the
target design.

## Data flow

```
user prompt (natural language)
   │
   ▼
[orchestrator]  ── built LAST, wires the modules; each module is also
   │               runnable standalone with file-based inputs/outputs
   ▼
[[module-1-design]]      text → Gemma → CadQuery Python → executed →
   │                     parametric STEP/STL solid (self-correction loop)
   ▼  geometry (STEP/STL) + design metadata
[[module-2-simulation]]  deterministic geometry checks + FEA (CalculiX/FreeCAD)
   │
   ▼  simulation results (checks report + FEA fields)
[[module-3-analysis]]    Gemma reads results → technical summary for a human
```

Failures propagate as feedback, not just downstream: simulation findings can
drive a redesign iteration in Module 1 (the old repo proved this loop with
PyBullet drop/push tests driving redesign).

## Module contracts

- Modules communicate through **files + typed schemas** (to live in `shared/`),
  not imports of each other's internals. That is what makes isolated build and
  test possible.
- Each module ships its own tests and a standalone CLI entry point.
- Module 1's LLM calls go through the shared provider layer described in
  [[infra-gemma-vllm-amd]] — Gemma on vLLM/AMD MI300X primary, explicit
  (never silent) fallbacks.

## Cross-cutting rules

- Parametric code-CAD only; mesh text-to-3D rejected — see [[decisions]].
- All HTTP/LLM errors must surface with real details; the safebrowse.io
  incident in [[infra-gemma-vllm-amd]] is the canonical cautionary tale.

## Build order

1. [[module-1-design]] (in isolation, file-out STEP/STL)
2. [[module-2-simulation]]
3. [[module-3-analysis]]
4. Orchestrator wiring + end-to-end run
