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
