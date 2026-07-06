# agentic-mechanical-engineer — project conventions

## What this repo is

Rebuild of the AMD Hackathon ACT II Track 3 project: natural-language prompt →
mechanical part design (Gemma → CadQuery → STEP/STL) → simulation → analysis.
Built **module by module**; each module must run and pass its tests in full
isolation before the next module is started. Do not start a new module while the
current one is unfinished.

## Wiki (source of truth for project knowledge)

- All conventions live in `wiki/SCHEMA.md` — read it before touching `wiki/`.
- Pages live in `wiki/pages/`, use YAML frontmatter
  (`type,title,status,tags,updated,sources`) and `[[wikilink]]` links.
- `wiki/index.md` is generated from frontmatter (gitignored — rebuild, don't edit).
- `wiki/log.md` is append-only; every wiki maintenance run adds a dated entry.
- Ground wiki claims about code in `path:line` references.

### /wiki-update (primary maintenance path — manual)

When the user says `/wiki-update` (optionally with a git range, e.g.
`/wiki-update HEAD~3..HEAD`), invoke the `wiki-maintainer` skill
(`.claude/skills/wiki-maintainer/SKILL.md`). Default range: latest commit
(`HEAD~1..HEAD`) plus uncommitted changes. The skill NEVER auto-commits — show
the wiki diffs and wait for the user to confirm/commit.

An optional post-commit hook (`scripts/hooks/post-commit`) can run this
headlessly, but it is disabled by default; see README for the enable step.

## Engineering conventions

- **Parametric code-CAD only.** Designs are CadQuery Python producing valid
  STEP/STL solids. Mesh text-to-3D is rejected — not physics-valid for MechE
  (see `wiki/pages/decisions.md`).
- **Surface real errors.** LLM/HTTP calls must raise or report the actual
  failure (status code, content-type, body snippet) — never silently fall back.
  A safebrowse.io content filter on the dev laptop intercepts plain-HTTP calls
  to the bare droplet IP:port and returns an HTML redirect; silent fallbacks
  hide this class of failure (see `wiki/pages/infra-gemma-vllm-amd.md`).
- **Provider layer** lives in `shared/` and is provider-agnostic: primary is
  Gemma on vLLM/AMD MI300X (OpenAI-compatible); Fireworks/OpenRouter are
  non-Gemma fallbacks — but fallback selection must be explicit, never silent.
- **Small commits**, imperative subject lines.
- `raw/` is immutable: source documents go in, nothing is ever edited there.
