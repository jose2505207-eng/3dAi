"""Minimal OpenAI-compatible chat client (stdlib only — no extra deps).

Primary target: Gemma on vLLM / AMD MI300X (VLLM_BASE_URL). Any
OpenAI-compatible endpoint works; provider selection is explicit
configuration, never a silent fallback.

Error doctrine (binding, see wiki/pages/infra-gemma-vllm-amd.md):
- Every failure surfaces the real evidence: HTTP status, Content-Type,
  redirect target, and the first ~500 chars of the body.
- An HTML body is detected and labeled as probable proxy/content-filter
  interception (the safebrowse.io lesson), distinct from a normal error.
- Redirects are NOT followed: a 3xx from a bare IP:port endpoint is how the
  content filter answers, so it must be reported, not obeyed.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

DEFAULT_MODEL = "google/gemma-3-27b-it"
BODY_SNIPPET_CHARS = 500

HTML_HINT = ("endpoint returned HTML, likely a proxy/filter intercepted the "
             "request — check network path (tunnel to the droplet or use TLS)")


class LLMError(Exception):
    """LLM call failed. The message always carries the real evidence
    (status / content-type / body snippet); `kind` classifies it."""

    def __init__(self, kind: str, detail: str):
        super().__init__(f"[{kind}] {detail}")
        self.kind = kind      # config | network | http_error | html_response | bad_json | bad_shape
        self.detail = detail


@dataclass
class CallRecord:
    """Provenance for one real HTTP round-trip to the model endpoint."""

    called: bool
    endpoint: str
    model: str
    http_status: int | None = None
    response_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_s: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None  # surface 3xx to the caller instead of following it


_OPENER = urllib.request.build_opener(_NoRedirect)


def _body_snippet(raw: bytes) -> str:
    return raw[:BODY_SNIPPET_CHARS].decode("utf-8", errors="replace")


def _looks_like_html(content_type: str, body: str) -> bool:
    return "text/html" in content_type.lower() or body.lstrip()[:1] == "<"


def _request(url: str, payload: dict | None, headers: dict, timeout_s: float) -> dict:
    """One HTTP round-trip. Returns parsed JSON or raises LLMError with the
    real status / content-type / body evidence."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with _OPENER.open(req, timeout=timeout_s) as resp:
            raw = resp.read()
            status = resp.status
            ctype = resp.headers.get("Content-Type", "?")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = _body_snippet(raw)
        location = exc.headers.get("Location") if exc.headers else None
        detail = (f"HTTP {exc.code} from {url}"
                  + (f" (redirect to {location})" if location else "")
                  + f"; content-type {exc.headers.get('Content-Type', '?') if exc.headers else '?'}"
                  + f"; body starts: {body!r}")
        if _looks_like_html(exc.headers.get("Content-Type", "") if exc.headers else "", body) \
                or (300 <= exc.code < 400):
            raise LLMError("html_response", f"{HTML_HINT}. {detail}") from exc
        raise LLMError("http_error", detail) from exc
    except urllib.error.URLError as exc:
        raise LLMError("network", f"request to {url} failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMError("network", f"request to {url} timed out after {timeout_s}s") from exc

    body = _body_snippet(raw)
    if _looks_like_html(ctype, body):
        raise LLMError("html_response",
                       f"{HTML_HINT}. HTTP {status} from {url}; content-type {ctype}; "
                       f"body starts: {body!r}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError("bad_json",
                       f"non-JSON response: HTTP {status} from {url}; content-type {ctype}; "
                       f"body starts: {body!r}") from exc


@dataclass
class LLMClient:
    """OpenAI-compatible /v1 endpoint client. `base_url` must end in /v1."""

    base_url: str
    model: str = DEFAULT_MODEL
    api_key: str = ""
    timeout_s: float = 180.0
    _headers: dict = field(init=False, repr=False)

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key or 'none'}"}

    @classmethod
    def from_env(cls) -> "LLMClient":
        base_url = os.environ.get("VLLM_BASE_URL", "").strip()
        if not base_url:
            raise LLMError("config",
                           "VLLM_BASE_URL is not set — refusing to run. Set it to the "
                           "OpenAI-compatible base URL, e.g. http://<droplet>:8000/v1")
        return cls(base_url=base_url,
                   model=os.environ.get("MODEL_NAME", DEFAULT_MODEL),
                   api_key=os.environ.get("LLM_API_KEY", ""),
                   timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "180")))

    def preflight(self) -> dict:
        """GET {base_url}/models. Raises LLMError (with real evidence) if the
        endpoint is unreachable or answers with anything but JSON."""
        url = f"{self.base_url}/models"
        data = _request(url, None, self._headers, min(self.timeout_s, 15.0))
        if "data" not in data:
            raise LLMError("bad_shape",
                           f"{url} returned JSON without a 'data' field — not an "
                           f"OpenAI-compatible /models reply: {str(data)[:300]!r}")
        return data

    def chat(self, system: str, user: str, temperature: float = 0.4) -> tuple[str, CallRecord]:
        """One /chat/completions round-trip. Returns (text, provenance record).
        On failure raises LLMError; the caller owns retry policy."""
        url = f"{self.base_url}/chat/completions"
        record = CallRecord(called=True, endpoint=url, model=self.model)
        t0 = time.monotonic()
        try:
            data = _request(url, {
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": temperature,
            }, self._headers, self.timeout_s)
        except LLMError as exc:
            record.latency_s = round(time.monotonic() - t0, 3)
            record.error = str(exc)
            exc.call_record = record  # type: ignore[attr-defined]
            raise
        record.latency_s = round(time.monotonic() - t0, 3)
        record.http_status = 200
        record.response_id = data.get("id")
        usage = data.get("usage") or {}
        record.prompt_tokens = usage.get("prompt_tokens")
        record.completion_tokens = usage.get("completion_tokens")
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("bad_shape",
                           f"JSON reply missing choices[0].message.content: "
                           f"{str(data)[:300]!r}") from exc
        return text, record
