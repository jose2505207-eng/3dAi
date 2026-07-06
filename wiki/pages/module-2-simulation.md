---
type: module
title: "Module 2 — Simulation: deterministic checks + FEA"
status: planned
tags: [simulation, fea, calculix, freecad, validation]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
---

# Module 2 — Simulation

**Status: planned.** Built only after [[module-1-design]] is done and tested in
isolation. Detailed spec is deliberately deferred; this records the agreed shape.

## Spec (outline)

Input: STEP/STL geometry + design metadata from Module 1 (via files + shared
schemas). Output: a machine-readable simulation report for [[module-3-analysis]].

Two layers, cheap-first:

1. **Deterministic checks** — no solver needed: solid validity/watertightness,
   bounding box & mass properties vs. request, minimum wall thickness, hole
   sizes/positions. Fast, always run, and their failures feed Module 1's
   redesign loop.
2. **FEA** — CalculiX (likely driven through FreeCAD's FEM workbench) for
   stress/displacement under specified load cases. Meshing + boundary
   conditions derived from design metadata.

The old repo also used PyBullet drop/push rigid-body tests to drive redesign;
whether that returns here is an open question to settle when this module starts.

## Constraints

- Consumes only Module 1's file outputs — no imports of Module 1 internals.
- Solver failures surface with real logs; a check that could not run is
  reported as "not run", never as "passed".

Links: [[architecture]] · [[module-1-design]] · [[module-3-analysis]]
