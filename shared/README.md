# shared/ — provider layer + shared schemas (stub)

Not implemented yet. Will contain, when Module 1 is built:

- `providers/` — one client interface, multiple backends:
  - `vllm` (primary): Gemma on the AMD MI300X droplet, OpenAI-compatible API.
  - `fireworks`, `openrouter` (fallbacks, non-Gemma).
  Backend selection is explicit configuration; a failing backend must raise the
  real HTTP error (status, content-type, body snippet) — never silently switch.
- `schemas/` — dataclasses/pydantic models shared across modules
  (DesignRequest, DesignResult, SimResult, AnalysisReport).

See wiki/pages/infra-gemma-vllm-amd.md and wiki/pages/architecture.md.
