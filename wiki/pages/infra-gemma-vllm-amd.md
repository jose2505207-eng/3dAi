---
type: infra
title: "Infra: Gemma on vLLM / AMD MI300X + the safebrowse.io lesson"
status: implemented
tags: [gemma, vllm, amd, mi300x, providers, http, safebrowse]
updated: 2026-07-06
sources:
  - "project brief (2026-07-06)"
  - "mech-eng repo commits c345514, 7f28732 (env audit; surface real fallback reason)"
---

# Infra: Gemma on vLLM / AMD MI300X

`status: implemented` refers to the droplet/endpoint itself, which exists and
worked in the hackathon; the *code* that talks to it in this repo is not built yet.

## The serving stack (sponsor-critical)

- **Gemma** served by **vLLM** on an **AMD Developer Cloud MI300X droplet**,
  exposing an **OpenAI-compatible** HTTP endpoint (`/v1/chat/completions`).
- This Gemma-on-AMD path is the project's **key differentiator and prize
  target** — it must remain the primary, demonstrated path in every demo.
- The provider layer (to live in `shared/`) is nonetheless provider-agnostic:
  **Fireworks** and **OpenRouter** are configured as non-Gemma fallbacks. Base
  URL and model are configuration, not code. Fallback is **explicit** —
  selected by config or by a surfaced, logged decision — never a silent rescue.

## Hard-won lesson: the safebrowse.io interception

A network content filter (**safebrowse.io**) on the dev laptop intercepts
**plain-HTTP requests to the bare droplet `IP:port`** and returns an **HTML
redirect page** instead of the API response. Symptoms:

- The HTTP call "succeeds" (2xx/3xx), but the body is HTML, not JSON.
- Naive clients then fail with a confusing JSON parse error — or worse,
  a silent fallback hides that the primary endpoint was never reached, and you
  debug the wrong thing for hours.

### Rules derived from it (binding on all modules)

1. **Surface real HTTP errors.** Report status code, `Content-Type`, and a body
   snippet on every failure. Never swallow, never silently fall back.
2. **Validate the response shape** before parsing: an OpenAI-compatible reply is
   JSON; `text/html` means interception — say so explicitly in the error.
3. A configured-but-unreachable primary is an **error state**, not an automatic
   reroute; the old repo's fix "surface the real reason when generative mode
   falls back to template" is the precedent.

Practical mitigations when developing on the filtered network: tunnel to the
droplet (e.g. SSH port-forward to localhost) or put TLS/a domain in front of it,
so the filter has nothing to intercept.

Links: [[module-1-design]] · [[module-3-analysis]] · [[decisions]] · [[architecture]]
