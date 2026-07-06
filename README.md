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
  design/        Module 1: text → Gemma → CadQuery → STEP/STL   (working)
  simulation/    Module 2: deterministic checks + FEA           (planned)
  analysis/      Module 3: Gemma reads results, writes summary  (planned)
orchestrator/    wires the modules together (built last)
shared/          LLM provider layer (shared/llm.py) + shared schemas
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

## Module 1 — design (working)

Natural-language prompt → Gemma writes CadQuery → sandboxed execution →
geometry validation (valid, watertight, volume > 0) → STEP + STL, with a
self-correction loop that feeds the *real* error text back to Gemma (budget:
`CAD_MAX_ITERATIONS`, default 5). Every run writes a `run_record.json` with
per-iteration provenance (endpoint, model, response id, tokens) so a stub
answer can never masquerade as a real Gemma run.

### Setup

```sh
python3 -m venv .venv
.venv/bin/pip install cadquery pytest
```

### Run

```sh
export VLLM_BASE_URL=http://<droplet>:8000/v1   # required; no default
export MODEL_NAME=google/gemma-3-27b-it          # default
.venv/bin/python -m modules.design "a mounting bracket that holds 500 N with a safety factor of 2, under 200 g"
```

Outputs land in `outputs/design/<stamp>-<slug>/`: `part.step`, `part.stl`,
`part.py` (the final CadQuery script), `run_record.json`. Exit codes: 0 ok,
1 iteration budget exhausted, 2 configuration/endpoint failure.

Before the first LLM call the module **preflights** `GET $VLLM_BASE_URL/models`
and refuses to run if it is unreachable or answers non-JSON. An HTML body is
reported as probable proxy/content-filter interception (the safebrowse.io
lesson — see `wiki/pages/infra-gemma-vllm-amd.md`); there is **no silent
fallback** anywhere.

### Tests

```sh
.venv/bin/pytest modules/design/tests/            # offline suite (mocked LLM)
VLLM_BASE_URL=http://<droplet>:8000/v1 \
  .venv/bin/pytest modules/design/tests/test_live.py -v   # live Gemma smoke test
```

The live test skips gracefully when `VLLM_BASE_URL` is unset.

### Manual verification (network path to the droplet required)

Run the CLI from a network path that can actually reach the droplet — on the
droplet itself, or tethered; a laptop content filter that intercepts plain
HTTP to the bare `IP:port` will (by design) fail preflight with an explicit
"endpoint returned HTML" error. While the CLI runs, watch:

```sh
docker logs -f gemma
```

and confirm a `POST /v1/chat/completions 200` per iteration — that is the
proof the calls truly reached Gemma.

## Status

Module 1 (design) is **working**; Modules 2–3 and the orchestrator are
**planned**. See `wiki/pages/architecture.md` for the design,
`wiki/pages/module-1-design.md` for Module 1, and `wiki/pages/decisions.md`
for the why.
