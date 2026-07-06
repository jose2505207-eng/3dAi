# agentic-mechanical-engineer

Natural-language prompt → mechanical part design → simulation → analysis.

Rebuild of the AMD Developer Hackathon ACT II (Track 3) project, done **module by
module**: each module must run and be tested in full isolation before the next one
is started. The design LLM is **Gemma served via vLLM on an AMD MI300X droplet**
(OpenAI-compatible endpoint) — the Gemma-on-AMD path is the project's key
differentiator; the provider layer is nonetheless provider-agnostic.

## Layout

```
wiki/            LLM-maintained project wiki (start at wiki/SCHEMA.md)
raw/             immutable source docs (papers, tool docs) — never edited
modules/
  design/        Module 1: text → Gemma → CadQuery → STEP/STL   (planned)
  simulation/    Module 2: deterministic checks + FEA           (planned)
  analysis/      Module 3: Gemma reads results, writes summary  (planned)
orchestrator/    wires the modules together (built last)
shared/          LLM provider layer + shared schemas (stub)
scripts/hooks/   opt-in git hooks (disabled until symlinked)
```

## Wiki

The wiki under `wiki/` is the project's living documentation. Conventions
(frontmatter, wikilinks, maintenance workflows) are defined in
[wiki/SCHEMA.md](wiki/SCHEMA.md). `wiki/index.md` is **generated** from page
frontmatter and gitignored; `wiki/log.md` is an append-only operation log.

To update the wiki after code changes, the **primary path is manual**: ask Claude
Code for `/wiki-update` (see `CLAUDE.md`), which invokes the
`wiki-maintainer` skill. The skill never commits — it shows diffs for you to review.

### Optional: auto-update on commit (disabled by default)

`scripts/hooks/post-commit` runs the wiki maintainer headlessly after each commit.
It is intentionally **not installed** (per-commit headless runs cost tokens; test
the skill manually first). Enable it with one line:

```sh
ln -s ../../scripts/hooks/post-commit .git/hooks/post-commit
```

Disable it again by removing the symlink: `rm .git/hooks/post-commit`.

## Status

All three modules and the orchestrator are **planned** — this repo currently
contains only structure, wiki, and tooling. See `wiki/pages/architecture.md` for
the design and `wiki/pages/decisions.md` for the why.
