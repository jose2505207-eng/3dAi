# Wiki schema & maintenance (read this before editing wiki/)

Karpathy-style LLM wiki: a small set of densely linked pages, each owning one
topic, maintained by an LLM (the `wiki-maintainer` skill) and reviewed by a human.
Prose is grounded in sources — `path:line` references for code claims, `raw/`
files or URLs for external claims.

## Layout

```
wiki/
  SCHEMA.md    this file — conventions + maintenance workflows (hand-edited)
  index.md     GENERATED table of contents, built from page frontmatter.
               Gitignored; never hand-edit; rebuild via the lint/update workflows.
  log.md       append-only operation log; newest entry at the BOTTOM.
               Existing entries are never edited or deleted.
  pages/       one topic per file, kebab-case filenames (e.g. module-1-design.md)
```

## Page frontmatter (YAML, required on every page in pages/)

```yaml
---
type: architecture        # architecture | module | infra | decision | reference
title: "Human-readable title"
status: planned           # planned | in-progress | implemented | deprecated
tags: [gemma, cadquery]   # lowercase kebab-case, 1–6 tags
updated: 2026-07-06       # ISO date of last substantive edit (not typo fixes)
sources:                  # where the page's claims come from
  - "project brief (2026-07-06)"          # a prompt/conversation
  - "modules/design/generator.py:42"      # a code path:line
  - "raw/cadquery-docs.md"                # an immutable source doc
  - "https://example.com/..."             # a URL
---
```

Field semantics:

- **type** — exactly one of the five values above. `decision` pages record
  choices + rationale; `infra` pages record environments/endpoints/ops lessons;
  `reference` pages summarize external material (usually paired with a `raw/` file).
- **status** — lifecycle of the *thing the page describes* (for `module` pages,
  the module itself). Non-module pages that are simply "current" use
  `implemented`. `deprecated` pages are kept for history, not deleted.
- **updated** — bumped only on substantive content changes.
- **sources** — every non-obvious claim in the body must be traceable to one of
  these. Code claims cite `path:line`.

## Wikilinks

- `[[page-slug]]` links to `wiki/pages/page-slug.md` (slug = filename without
  `.md`). Optional display text: `[[page-slug|shown text]]`.
- Link liberally; a `[[slug]]` with no matching file is a **red link** — allowed
  as a marker for a page worth writing, but the lint workflow must list red
  links so they are deliberate, not typos.

## Maintenance workflows

Executed by the `wiki-maintainer` skill (`.claude/skills/wiki-maintainer/SKILL.md`);
manual entry point is `/wiki-update` (see CLAUDE.md). All workflows end by
rebuilding `index.md`, appending to `log.md`, and showing diffs — **never
auto-committing**.

1. **ingest** — a new source document arrives: store it verbatim in `raw/`
   (immutable), then create/update the relevant `pages/*.md` summarizing it,
   citing the `raw/` file in `sources`.
2. **update-from-diff** — code changed: read the git diff (given range, else
   `HEAD~1..HEAD` + uncommitted changes), map changed paths to pages
   (`modules/design/` → `module-1-design`, `modules/simulation/` →
   `module-2-simulation`, `modules/analysis/` → `module-3-analysis`,
   `shared/`+endpoint config → `infra-gemma-vllm-amd`, cross-module/
   `orchestrator/` → `architecture`), and update status/behavior/data-flow
   descriptions with fresh `path:line` citations.
3. **lint** — consistency pass: validate frontmatter (fields present, enum
   values legal, `updated` is a date), check wikilinks (report red links),
   verify cited `path:line` targets still exist, rebuild `index.md`.

## index.md generation

Built from frontmatter only: pages grouped by `type` (order: architecture,
module, infra, decision, reference), each line
`- [[slug|title]] — status, updated YYYY-MM-DD`. A generated-file banner comment
goes at the top. index.md is gitignored, so rebuild it whenever it's missing.

## log.md entry format

```markdown
## 2026-07-06 — <operation> (<workflow: ingest|update-from-diff|lint|bootstrap>)
- what changed, one bullet per page touched
- source: <git range / raw file / prompt>
```

## Defaults chosen where the brief was ambiguous (noted per SCHEMA policy)

- `status` enum is `planned | in-progress | implemented | deprecated`; `title`
  and `tags` value shapes as specified above — the brief named the fields but
  not their domains.
- `log.md` appends at the **bottom** (true append-only; friendlier to diffs).
- `index.md` is gitignored per the brief, so it exists only locally and must be
  regenerated after clone; the lint workflow does this.
- Red links (dangling `[[wikilinks]]`) are allowed but must be reported by lint.
- `sources` entries are free-form strings in the four shapes shown above, not a
  structured object — cheap to write, easy to grep.
- Page slugs are kebab-case and stable; renaming a page requires updating all
  inbound wikilinks (lint catches strays).
