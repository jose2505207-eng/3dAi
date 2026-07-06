---
name: wiki-maintainer
description: Sync wiki/pages/*.md with the latest code changes — update page status/behavior/data-flow from a git diff with path:line grounding, fix wikilinks, rebuild wiki/index.md from frontmatter, and append a dated entry to wiki/log.md. Never commits; always ends by showing diffs for the user to confirm. Invoke for /wiki-update (optionally with a git range like HEAD~3..HEAD).
---

# wiki-maintainer

Keep the wiki in `wiki/` synchronized with the code. All conventions
(frontmatter fields, status enum, wikilink rules, index format, log format) are
defined in `wiki/SCHEMA.md` — read it first and follow it exactly.

## Inputs

- Optional git range argument (e.g. `HEAD~3..HEAD`, `abc123..def456`).
- Default when no range is given: `HEAD~1..HEAD` **plus** uncommitted changes
  (`git diff HEAD` and untracked files under the code directories).

## Steps (do exactly these, in order)

1. **Read the diff.** `git diff <range> --stat` then the full diff for changed
   paths under `modules/`, `orchestrator/`, `shared/`, and `scripts/`. Ignore
   changes that only touch `wiki/` (avoid self-referential updates) and pure
   formatting noise.

2. **Update matching pages.** Map each changed code path to its page:
   - `modules/design/` → `wiki/pages/module-1-design.md`
   - `modules/simulation/` → `wiki/pages/module-2-simulation.md`
   - `modules/analysis/` → `wiki/pages/module-3-analysis.md`
   - `shared/` (provider layer, schemas, endpoint config) → `wiki/pages/infra-gemma-vllm-amd.md`
   - `orchestrator/` or cross-module changes → `wiki/pages/architecture.md`
   For each affected page: update `status` (planned → in-progress →
   implemented) to match reality, revise behavior and data-flow prose, bump
   `updated`, and **ground every claim about code in `path:line` references**
   added to the prose and/or `sources`. Verify each cited `path:line` exists
   before writing it. If a change fits no existing page, create one per
   SCHEMA.md rather than forcing it into the wrong page.

3. **Fix wikilinks and rebuild the index.** Check every `[[wikilink]]` in
   `wiki/pages/*.md` resolves to a file; repair typos, list surviving red links
   explicitly. Then regenerate `wiki/index.md` from page frontmatter using the
   exact format in SCHEMA.md (grouped by type; generated-file banner; it is
   gitignored — rebuild it even if missing).

4. **Append to the log.** Add a dated entry at the **bottom** of `wiki/log.md`
   in the SCHEMA.md format: what changed, one bullet per page touched, and the
   source (the git range). Never edit or delete existing entries.

5. **Show, don't commit.** NEVER run `git commit` (or `git add`). Finish by
   showing `git diff -- wiki/` (plus new-file contents for any created pages)
   and a one-paragraph summary, then let the user review and commit themselves.
   This rule holds even in headless/hook invocations.

## Guardrails

- Only claim what the diff + code show; when the diff is ambiguous about
  behavior, read the actual files rather than guessing.
- Don't rewrite pages wholesale — make targeted edits so the review diff stays
  small.
- Respect the project's error-surfacing doctrine: if you notice code that
  silently swallows errors, flag it in your summary (and it may warrant a note
  in the wiki), but don't change code — this skill touches only `wiki/`.
