---
type: module
title: "Module 2 — Simulation: deterministic checks + FEA"
status: implemented
tags: [simulation, checks, validation, materials, fea, calculix, gmsh]
updated: 2026-07-07
sources:
  - "project brief (2026-07-06)"
  - "modules/simulation/checks.py:210"
  - "modules/simulation/geometry.py:26"
  - "modules/simulation/materials.py:19"
  - "modules/simulation/mesher.py:53"
  - "modules/simulation/ccx.py:69"
  - "modules/simulation/fea.py:95"
  - "shared/schemas.py:31"
  - "modules/simulation/__main__.py:22"
---

# Module 2 — Simulation

**Status: implemented.** Layer 1 (deterministic checks) and Layer 2 (static
FEA: gmsh + CalculiX) are both built and tested — 20 offline tests, no
network. Open follow-ups: min-wall-thickness stays `not_run`, and the old
repo's PyBullet drop/push tests remain an open question.

## Layer 1 — deterministic checks (as built)

Input: a [[module-1-design]] run dir (`part.step`, `part.stl`,
`run_record.json`), consumed **as files only** — no `modules.design` imports
(modules/simulation/checks.py:210 reads `run_record.json` as plain JSON).
Output: `sim_report.json` (schema `sim_report/v1`, shared/schemas.py:53)
written into the same run dir — this file is [[module-3-analysis]]'s input.
CLI: `python -m modules.simulation <run-dir>`; exit 0 = no check failed,
1 = a check failed, 2 = not a Module 1 run dir / IO error
(modules/simulation/__main__.py:22,42,48).

### Honesty rule (binding, enforced in the schema)

Every check is `pass | fail | not_run`. A check that could not run is
`not_run` **with the reason** — never `pass`, never omitted. The schema makes
a reason-less fail/not_run unconstructible (shared/schemas.py:31). Overall
verdict: `fail` if anything failed, `pass` only if everything passed, else
`incomplete` (shared/schemas.py:65). Same doctrine as `shared/llm.py`
([[infra-gemma-vllm-amd]]).

### The checks

| check | what it does |
|---|---|
| `geometry_valid` | re-imports the STEP; ≥1 solid, volume > 0, OCCT-valid, watertight — mirror of Module 1's gate (modules/simulation/checks.py:53, geometry.py:26,52). An unloadable STEP fails with the real importer error; the other checks then go `not_run`, not `pass`. |
| `single_body` | fails with the count if the STEP holds >1 solid (modules/simulation/checks.py:73) — catches disconnected unions (a live bracket run produced 2). |
| `bounding_box` | reports the bbox; compares parameters whose name tokens imply overall dimensions (l/w/h/length/width/height/thick/... — checks.py:26). Oversized parameter ⇒ fail; unmatched-but-fits ⇒ `not_run` (could be an interior dimension); no dimension-named parameters ⇒ `not_run` with the bbox still reported (checks.py:82). |
| `mass_budget` | volume × density. Material is config: env `MATERIAL` against a 10-entry density table; unset ⇒ named default assumption `aluminum_6061` 2.70 g/cm³ (modules/simulation/materials.py:40). Compared against a `max_mass`/`mass_limit`-named run_record parameter (grams assumed — checks.py:28,115). Binding pass/fail **only with explicit MATERIAL**; a default-assumption density makes the comparison `not_run` (assumption-based, mass still reported); an unknown MATERIAL claims no mass at all. |
| `min_wall_thickness` | honest `not_run` in Layer 1 — needs medial-axis/offset analysis; refuses to approximate from the bbox (checks.py:162). |
| `hole_geometry` | best-effort: cylindrical faces (radius via `BRepAdaptor_Surface`, geometry.py:43) vs hole-diameter/radius-named parameters; `not_run` when no expectation is derivable; evidence notes that bosses count too — concavity is not analyzed (checks.py:172). |

### Provenance

The report records sha256 + size of every consumed input, timestamp, and the
design run's prompt/model/endpoint echoed from `run_record.json`
(checks.py:210, shared/schemas.py:86). `part.stl` is hashed but unused by
Layer 1; its absence is noted as a contract violation, not an error.

### Tests

`.venv/bin/pytest modules/simulation/tests/` — synthetic solids built
directly with cadquery (never via modules.design): 60×40×5 box for exact
bbox/mass math (12 cm³ ⇒ steel 94.44 g, assumed-aluminum 32.4 g), a two-solid
compound failing `single_body` with count 2, missing/unknown MATERIAL ⇒
`not_run` (never pass), hole pass/fail, CLI exit codes, and the schema
refusing reason-less failures (modules/simulation/tests/test_checks.py).

## Layer 2 — static FEA (as built)

Pipeline: gmsh SDK meshes `part.step` to 2nd-order tets (C3D10) and writes
the Abaqus-format mesh itself — gmsh owns the gmsh→Abaqus midside-node
reordering (modules/simulation/mesher.py:53,78,105; a physical volume group
keeps stray section-less 2D shells out of the deck, mesher.py:68-71). We
append node sets / material / static step cards and run `ccx`
(modules/simulation/ccx.py:50,69), then parse max von Mises and max
displacement from the fixed-width `.frd` (ccx.py:93). Raw artifacts stay in
`<run-dir>/fea/` (mesh.inp, job.inp, job.frd, ccx.log). The `fea_static`
check joins the Layer 1 checks and the overall verdict; a `fea{}` block
(mesh stats, material, assumed BCs, results, solver paths) extends
`sim_report.json` (shared/schemas.py:61). CLI: `--no-fea`, `--mesh-size`,
`--fea-timeout` (modules/simulation/__main__.py:28-33).

### Boundary conditions — documented heuristic, recorded for audit

Deriving BCs automatically is hard; the heuristic is explicit and its every
choice lands verbatim in `fea.boundary_conditions` (modules/simulation/fea.py:95):

- **Fixed:** the lowest-Z group of cylindrical (hole) faces — ties within
  10% of part height (fea.py:43,108) — all DOFs ("mounting holes nearest
  the base").
- **Load:** highest-Z planar face ≥ 5% of the bbox footprint, loaded −Z
  (assumption) with consistent TRI6 nodal loads — midsides carry area/3,
  shares on fixed nodes are excluded and the total rescaled exact
  (fea.py:51).
- **Magnitude:** load/force-named run_record parameter, else `"<number> N"`
  parsed from the design prompt; source recorded (fea.py:73). Safety factor:
  parameter or prompt, else recorded default assumption 2.0 (fea.py:85,92).

Unresolvable BCs, missing ccx (install hint: `sudo apt-get install -y
calculix-ccx`, ccx.py:17), unknown material, mesh or solver failure ⇒
`fea_static` is `not_run` with the real evidence (solver log tail kept) —
the solver is never stubbed and never silently passed.

**Verdict:** `max_von_mises <= yield / safety_factor`; yield/E/ν come from
the same MATERIAL config as the mass check, now with elastic properties per
material (modules/simulation/materials.py:19; default assumption
aluminum_6061: E 68.9 GPa, ν 0.33, yield 276 MPa).

### Layer 2 tests

Analytic anchor: a 100×10×10 mm tension bar under 1000 N with 3-2-1
restraint — parsed max von Mises must match σ = F/A = 10 MPa (±7%) and
displacement FL/AE (±10%) (modules/simulation/tests/test_fea.py:50). Plus:
BC-heuristic assertions on the 4-hole plate, no-holes / no-load-magnitude ⇒
`BCUnresolvable`, hand-built `.frd` parser fixture, full-pipeline fea block,
missing-ccx ⇒ `not_run` with install hint. ccx-gated tests skip when the
solver is absent. Toolchain install is documented in
modules/simulation/README.md (venv pip gmsh; apt calculix-ccx — needed on
the droplet too).

Links: [[architecture]] · [[module-1-design]] · [[module-3-analysis]]
