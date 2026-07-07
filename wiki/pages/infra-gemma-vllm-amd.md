---
type: infra
title: "Infra: Gemma on vLLM / AMD MI300X + the safebrowse.io lesson"
status: implemented
tags: [gemma, vllm, amd, mi300x, providers, http, safebrowse]
updated: 2026-07-07
sources:
  - "project brief (2026-07-06)"
  - "mech-eng repo commits c345514, 7f28732 (env audit; surface real fallback reason)"
  - "shared/llm.py:144"
  - "Dockerfile:14"
---

# Infra: Gemma on vLLM / AMD MI300X

The droplet/endpoint exists and worked in the hackathon; the code that talks
to it now lives in `shared/llm.py` — a stdlib-only OpenAI-compatible client
built for [[module-1-design]]. Configuration: `VLLM_BASE_URL` (required, no
default — shared/llm.py:133), `MODEL_NAME` (default `google/gemma-3-27b-it`),
`LLM_API_KEY`, `LLM_TIMEOUT_S`. It provides `preflight()` — `GET /models`,
refusing non-JSON (shared/llm.py:144) — and `chat()`, which returns the text
plus a `CallRecord` (endpoint, model, HTTP status, response id, token usage,
latency — shared/llm.py:43) as real-call provenance.

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

### Rules derived from it (binding on all modules, now enforced in shared/llm.py)

1. **Surface real HTTP errors.** Report status code, `Content-Type`, redirect
   target, and the first ~500 chars of the body on every failure
   (shared/llm.py:26,90-99). Never swallow, never silently fall back.
2. **Validate the response shape** before parsing: an OpenAI-compatible reply
   is JSON; an HTML body raises a distinctly-labeled `html_response` error —
   "endpoint returned HTML, likely a proxy/filter intercepted the request"
   (shared/llm.py:28,104-108). Redirects are never followed: a 3xx is
   surfaced with its `Location`, because that is how the filter answers
   (shared/llm.py:60).
3. A configured-but-unreachable primary is an **error state**, not an automatic
   reroute: Module 1 preflights `GET /models` before the first LLM call and
   refuses to run on failure (modules/design/loop.py:136); an LLM failure
   mid-loop aborts with the evidence instead of retrying or falling back
   (modules/design/loop.py:157).

Practical mitigations when developing on the filtered network: tunnel to the
droplet (e.g. SSH port-forward to localhost) or put TLS/a domain in front of it,
so the filter has nothing to intercept.

## Container (hackathon eligibility) and deployment

Single root `Dockerfile`, no compose. Two verified gotchas baked into it:

- Base is `python:3.11-slim-bookworm`, **pinned deliberately** — Debian
  trixie (the current `python:*-slim` default) dropped the `calculix-ccx`
  package ("no installation candidate", verified 2026-07-07); bookworm
  ships 2.20-1 (Dockerfile:28).
- The gmsh/cadquery wheels dlopen GL/X libraries even headless; each apt
  package in the image is justified by a named failure — `libGLU.so.1` from
  a bare-host `import gmsh`, the libxcursor1…libgomp1 block from
  `ldd libgmsh.so` "not found" lines (Dockerfile:33).

cadquery/gmsh/pytest/fastapi/uvicorn install into the image's **system
python, no venv**: the design sandbox spawns `python -I` subprocesses, so
cadquery must be importable by the image interpreter itself; the heavy pip
layer sits before the source copy to cache independently of code edits
(Dockerfile:52-55). Verified in-image: ccx 2.20 on PATH, all module tests
pass with the ccx-gated FEA tests running (design 17+1 skip, simulation
20/20). No endpoint or secret is baked in — `VLLM_BASE_URL`, `MODEL_NAME`,
`MATERIAL`, `CAD_MAX_ITERATIONS`, `UI_USER`, `UI_PASSWORD` are runtime env.

**Droplet deployment** (co-located with Gemma, documented at Dockerfile:14):
the UI container runs with `--network host` so `localhost:8000` reaches
vLLM; uvicorn binds **127.0.0.1** so the app is reachable only through
`cloudflared tunnel --url http://localhost:8080` (quick tunnel, no domain or
Cloudflare account — prints an `https://<random>.trycloudflare.com` URL),
never directly on the droplet's public IP. Auth is a mandatory shared HTTP
Basic credential (see [[architecture]]). Quick-tunnel caveat: the URL
changes whenever cloudflared restarts.

Links: [[module-1-design]] · [[module-3-analysis]] · [[decisions]] · [[architecture]]
