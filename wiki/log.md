# Wiki operation log

Append-only; newest entry at the bottom. Format defined in wiki/SCHEMA.md.

## 2026-07-06 — repo + wiki bootstrap (workflow: bootstrap)

- Created wiki/SCHEMA.md (conventions, frontmatter spec, workflows, defaults).
- Seeded pages: architecture, module-1-design, module-2-simulation,
  module-3-analysis, infra-gemma-vllm-amd (incl. safebrowse.io lesson),
  decisions (D-001…D-005).
- Built wiki/index.md from page frontmatter (generated, gitignored).
- source: project brief (2026-07-06); mech-eng repo commit history for
  prior-art references.

## 2026-07-06 — post-commit hook documented (workflow: update-from-diff)

- decisions.md: added Implementation note to D-005 — hook exists at
  scripts/hooks/post-commit, disabled-by-default (symlink enable, :5),
  wiki-only-commit skip (:22), WIKI_HOOK=off escape hatch (:14), never blocks
  the commit (:43); added the hook to sources.
- Wikilink check: all links resolve, no red links. index.md regenerated —
  identical to existing (no frontmatter changes), left as-is.
- source: git range HEAD~1..HEAD (e59d6df, "feat(hooks): opt-in post-commit
  wiki update trigger"); no uncommitted changes.

## 2026-07-06 — Module 1 (design) built and documented (workflow: update-from-diff)

- module-1-design.md: status planned → implemented ("working"); rewrote spec
  prose to as-built behavior — preflight (modules/design/loop.py:136), AST
  safety validation (modules/design/sandbox.py:56), python -I sandbox
  (modules/design/sandbox.py:98), watertight/valid/volume geometry validation
  (modules/design/runner.py:48, modules/design/sandbox.py:122-128),
  self-correction with real-error feedback (modules/design/prompts.py:44),
  CLI + exit codes (modules/design/__main__.py:31,62), run-record provenance
  (modules/design/loop.py:59), test suite incl. live smoke test
  (modules/design/tests/test_live.py:26); seeded the Gemma/CadQuery
  failure-pattern log (OCCT-fragile ops forbidden in the system prompt,
  modules/design/prompts.py:25).
- infra-gemma-vllm-amd.md: provider layer now real — shared/llm.py client
  (config shared/llm.py:133, preflight :144, CallRecord provenance :43);
  safebrowse rules marked as enforced with citations (html_response labeling
  shared/llm.py:28,104-108; no-follow redirects :60; preflight/abort
  modules/design/loop.py:136,157).
- Wikilink check: all links resolve, no red links. index.md regenerated
  (module-1-design now implemented).
- source: git range HEAD~4..HEAD (5d4be07 shared client, a1e2603 design
  module, 40420f9 tests, 60aa4c5 README); no uncommitted code changes.

## 2026-07-07 — Module 2 Layer 1 (deterministic checks) built (workflow: update-from-diff)

- module-2-simulation.md: status planned → in-progress; documented Layer 1
  as-built — files-only input contract (modules/simulation/checks.py:210),
  the six checks (geometry_valid checks.py:53, single_body :73,
  bounding_box :82, mass_budget :115 with MATERIAL config and named default
  assumption materials.py:34, min_wall_thickness honest not_run :162,
  hole_geometry :172), sim_report.json output + CLI exit codes
  (__main__.py:22,34,40), provenance hashing, offline test suite; Layer 2
  (FEA) remains planned.
- architecture.md: status planned → in-progress; "nothing implemented"
  intro replaced with per-module progress; Module contracts section marks
  the files+typed-schemas contract as realized (shared/schemas.py:19,31,53
  — pass|fail|not_run enum with mandatory reasons, sim_report/v1).
- Wikilink check: all links resolve, no red links. index.md regenerated
  (architecture and module-2-simulation now in-progress, updated 2026-07-07).
- source: git range HEAD~3..HEAD (7026de5 shared schemas, e6b0c76 simulation
  Layer 1, eea9af9 tests); no uncommitted code changes.

## 2026-07-07 — Module 2 Layer 2 (static FEA) built (workflow: update-from-diff)

- module-2-simulation.md: status in-progress → implemented; added the
  as-built Layer 2 section — gmsh C3D10 meshing with gmsh-owned Abaqus
  export (modules/simulation/mesher.py:53,78,105), ccx deck/run/parse
  (modules/simulation/ccx.py:50,69,93), documented BC heuristic recorded
  verbatim for audit (modules/simulation/fea.py:95 — lowest-Z hole group
  fixed fea.py:108, consistent TRI6 loads fea.py:51, load/SF sources
  fea.py:73,85), verdict max vM <= yield/SF with elastic properties in the
  materials table (materials.py:19), fea{} block in sim_report.json
  (shared/schemas.py:61), CLI flags (__main__.py:28-33), analytic
  tension-bar test anchor (tests/test_fea.py:50), toolchain install docs
  (modules/simulation/README.md). Honest not_run for missing ccx /
  unresolvable BCs / solver failure with log evidence.
- architecture.md: data-flow line corrected FEA (CalculiX/FreeCAD) →
  (gmsh + CalculiX) — FreeCAD is not used; progress line updated (Module 2
  built).
- Wikilink check: all links resolve, no red links. index.md regenerated
  (module-2-simulation now implemented).
- source: git range HEAD~4..HEAD (25aeaef schemas fea block, 8f491a3 FEA
  layer, 76c66b3 tests, 01cafee README); no uncommitted code changes.

## 2026-07-07 — Module 1 hardened against holeless/multi-body parts (workflow: update-from-diff)

- module-1-design.md: documented the two new geometry gates — exactly ONE
  solid (`solid_count > 1` now fails, modules/design/sandbox.py:154) and
  declared-holes-must-be-cut (hole/bore parameter with zero cylindrical
  faces fails, modules/design/sandbox.py:166; face census
  modules/design/runner.py:53); prompt rules added (single fused solid
  prompts.py:21, physically cut holes prompts.py:24); recorded the
  2026-07-07 live failure pattern (2-solid bracket with phantom
  hole_diameter caught by Module 2) and its fix verification;
  extract_parameters moved loop.py → sandbox.py:61; test count 15 → 17
  offline (new gate tests test_sandbox.py:49,61); refreshed shifted
  path:line citations; updated 2026-07-07.
- Wikilink check: all links resolve, no red links. index.md regenerated
  (module-1-design updated 2026-07-07).
- source: uncommitted changes (git diff HEAD — modules/design/{prompts,
  sandbox,runner,loop,tests/test_sandbox}.py); live runs
  outputs/design/20260707-172325-* (fail) and 20260707-182230-* (gates pass).
