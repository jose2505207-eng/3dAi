---
type: architecture
title: "System architecture: prompt → design → simulation → analysis"
status: implemented
tags: [architecture, pipeline, modules, orchestrator, web-ui]
updated: 2026-07-07
sources:
  - "project brief (2026-07-06)"
  - "shared/schemas.py:19"
  - "orchestrator/pipeline.py:48"
  - "orchestrator/server.py:60"
  - "orchestrator/static/index.html:56"
---

# System architecture

Natural-language prompt in, engineered part + technical report out. Three
independent modules plus an orchestrator, rebuilt from the hackathon repo
**module by module** — each module runs and is tested in full isolation before
the next is started. Progress: all three modules working
([[module-1-design]], [[module-2-simulation]], [[module-3-analysis]]) and
the orchestrator + web UI built and verified end-to-end (live pipeline run
through the browser, STL render confirmed in headless chromium).

## Data flow

```
user prompt (natural language)
   │
   ▼
[orchestrator]  ── run_pipeline() wires the modules; each module is also
   │               runnable standalone with file-based inputs/outputs
   ▼
[[module-1-design]]      text → Gemma → CadQuery Python → executed →
   │                     parametric STEP/STL solid (self-correction loop)
   ▼  geometry (STEP/STL) + design metadata
[[module-2-simulation]]  deterministic geometry checks + FEA (gmsh + CalculiX)
   │
   ▼  simulation results (checks report + FEA fields)
[[module-3-analysis]]    Gemma reads results → technical summary for a human
```

Failures propagate as feedback, not just downstream: simulation findings can
drive a redesign iteration in Module 1 (the old repo proved this loop with
PyBullet drop/push tests driving redesign).

## Orchestrator + web UI (as built)

`run_pipeline(prompt, out_dir, client, *, max_iterations=None, with_fea=True)`
(orchestrator/pipeline.py:48) chains the three modules' real entry points
and is honest about partial failure: a design failure STOPS the run (no
geometry to simulate); a simulation contract violation stops before
analysis; analysis **always** runs once a sim report exists — explaining a
fail/incomplete verdict is the point (orchestrator/pipeline.py:83) — and an
analysis failure keeps the design+sim artifacts. `PipelineResult` carries
per-stage status, verdict, artifact paths and the summary text
(orchestrator/pipeline.py:28).

The web UI (FastAPI + uvicorn) never blocks an HTTP request on the
minutes-long pipeline: `POST /run` returns a job id and runs the pipeline in
a background thread; the single-page UI polls `GET /status/{id}` and fetches
whitelisted artifacts via `GET /artifact/{id}/{name}`
(orchestrator/server.py:112,127,139). Demo scope, stated in code: in-memory
jobs (lost on restart), no concurrency cap (orchestrator/server.py:77).
Every route — including the static index page's `StaticFiles` mount, which a
router-level dependency would NOT cover — sits behind one shared HTTP Basic
credential enforced by middleware with constant-time compares
(orchestrator/server.py:60); missing `UI_USER`/`UI_PASSWORD` refuses to boot
(orchestrator/server.py:54, the no-silent-fallback doctrine). The page
renders stage progress, the verdict badge, the checks table (with honest
`not_run` rows), the fea block, marked-rendered `analysis.md`, and a
three.js 0.160.0 STL viewer (orchestrator/static/index.html:56). Deployment
(uvicorn on 127.0.0.1 behind a Cloudflare quick tunnel) is documented in the
Dockerfile and [[infra-gemma-vllm-amd]].

## Module contracts

- Modules communicate through **files + typed schemas** in `shared/`, not
  imports of each other's internals. That is what makes isolated build and
  test possible. Realized: `shared/schemas.py` — the `pass|fail|not_run`
  check enum (reason mandatory unless pass, shared/schemas.py:19,31) and
  `SimReport` (`sim_report/v1`), the Module 2 → Module 3 handoff file
  (shared/schemas.py:53); Module 2 consumes Module 1's run dir as files only
  (modules/simulation/checks.py:210).
- Each module ships its own tests and a standalone CLI entry point.
- Module 1's LLM calls go through the shared provider layer described in
  [[infra-gemma-vllm-amd]] — Gemma on vLLM/AMD MI300X primary, explicit
  (never silent) fallbacks.

## Cross-cutting rules

- Parametric code-CAD only; mesh text-to-3D rejected — see [[decisions]].
- All HTTP/LLM errors must surface with real details; the safebrowse.io
  incident in [[infra-gemma-vllm-amd]] is the canonical cautionary tale.

## Build order (all complete)

1. [[module-1-design]] (in isolation, file-out STEP/STL) — done
2. [[module-2-simulation]] — done
3. [[module-3-analysis]] — done
4. Orchestrator wiring + end-to-end run — done (verified live 2026-07-07:
   plate prompt → verdict `incomplete` with FEA pass, STL rendered in the
   browser through the tunnel)
