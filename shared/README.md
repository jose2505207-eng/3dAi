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
- `schemas/` (future) — models shared across modules
  (DesignRequest, DesignResult, SimResult, AnalysisReport).

See wiki/pages/infra-gemma-vllm-amd.md and wiki/pages/architecture.md.
