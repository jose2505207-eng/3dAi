# shared/ — provider layer + shared schemas

- `llm.py` — minimal OpenAI-compatible chat client (stdlib only). Primary:
  Gemma on vLLM / AMD MI300X via `VLLM_BASE_URL` (+ `MODEL_NAME`,
  `LLM_API_KEY`, `LLM_TIMEOUT_S`). Provides `preflight()` (GET `/models`,
  refuses non-JSON) and `chat()` (returns text + a `CallRecord` with
  endpoint, model, response id, token usage — real-call provenance).
  Every failure surfaces the real HTTP evidence (status, content-type,
  redirect target, body snippet); an HTML body is labeled as probable
  proxy/content-filter interception. Redirects are never followed.
  **No silent fallback** — Fireworks/OpenRouter would be explicit,
  configured choices, not rescues.
- `schemas.py` — typed contracts between modules (stdlib dataclasses, JSON
  on disk). `CheckResult` enforces the honesty enum pass|fail|not_run —
  fail/not_run require a reason, constructing a silent failure raises.
  `SimReport` (schema `sim_report/v1`) is Module 2's output / Module 3's
  input, with verdict pass|fail|incomplete and file-hash provenance helpers.

See wiki/pages/infra-gemma-vllm-amd.md and wiki/pages/architecture.md.
