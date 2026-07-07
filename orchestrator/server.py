"""Minimal web UI over the pipeline (FastAPI + uvicorn), behind Basic Auth.

    UI_USER=... UI_PASSWORD=... \
      uvicorn orchestrator.server:app --host 127.0.0.1 --port 8080

Bind to 127.0.0.1, NOT 0.0.0.0: the app is meant to be reached only through
the Cloudflare tunnel (`cloudflared tunnel --url http://localhost:8080`),
never directly on the droplet's public interface.

AUTH: one shared HTTP Basic credential from UI_USER/UI_PASSWORD, enforced by
middleware so EVERY route is covered — including the StaticFiles mount, which
a router-level dependency would NOT protect. Missing env → refuse to start
(no default credentials, same no-silent-fallback doctrine as the rest of the
repo).

DEMO SCOPE, deliberately: jobs live in an in-memory dict (lost on restart)
and there is NO concurrency cap (every POST /run spawns a thread — a
pipeline run is minutes of LLM + FEA).

The pipeline blocks for minutes, so POST /run returns a job id immediately
and the run happens in a background thread; the page polls GET /status.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.design.__main__ import default_out_dir
from orchestrator.pipeline import ARTIFACT_NAMES, run_pipeline
from shared.llm import LLMClient, LLMError


def _require_credentials() -> tuple[str, str]:
    user = os.environ.get("UI_USER", "")
    password = os.environ.get("UI_PASSWORD", "")
    if not user or not password:
        raise RuntimeError(
            "UI_USER and UI_PASSWORD must both be set — refusing to start the "
            "web UI without an auth gate (there is no default credential)")
    return user, password


UI_USER, UI_PASSWORD = _require_credentials()  # import-time: uvicorn won't boot without

app = FastAPI(title="agentic-mechanical-engineer")


@app.middleware("http")
async def basic_auth_gate(request: Request, call_next):
    ok = False
    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            user, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            user = password = ""
        # constant-time compares; & (not `and`) so both always run
        ok = bool(secrets.compare_digest(user.encode(), UI_USER.encode())
                  & secrets.compare_digest(password.encode(), UI_PASSWORD.encode()))
    if not ok:
        return Response(status_code=401, content="authentication required",
                        headers={"WWW-Authenticate":
                                 'Basic realm="agentic-mechanical-engineer"'})
    return await call_next(request)

JOBS: dict[str, dict] = {}  # in-memory only: lost on restart, no concurrency cap

ARTIFACT_MEDIA_TYPES = {
    "part.step": "application/octet-stream",
    "part.stl": "model/stl",
    "sim_report.json": "application/json",
    "analysis.md": "text/markdown",
}


class RunRequest(BaseModel):
    prompt: str


def _run_job(job_id: str, prompt: str, out_dir: Path) -> None:
    job = JOBS[job_id]
    job["state"] = "running"
    try:
        client = LLMClient.from_env()
        result = run_pipeline(prompt, out_dir, client,
                              on_stage=lambda s: job.__setitem__("stage", s))
    except LLMError as exc:            # config error (VLLM_BASE_URL unset)
        job.update(state="error", error=str(exc))
        return
    except Exception as exc:           # noqa: BLE001 — surface, never hang the poller
        job.update(state="error", error=f"{type(exc).__name__}: {exc}")
        return
    job.update(result.to_dict())
    job["state"] = "done" if result.ok else "error"
    if not result.ok:
        failed = result.stages.get(result.stage) or {}
        job["error"] = failed.get("error") or f"stage {result.stage} failed"


@app.post("/run")
def start_run(req: RunRequest) -> dict:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt is empty")
    job_id = uuid.uuid4().hex[:12]
    out_dir = default_out_dir(prompt)
    JOBS[job_id] = {"state": "queued", "stage": None, "prompt": prompt,
                    "out_dir": str(out_dir), "verdict": None, "artifacts": {},
                    "summary": None, "error": None}
    threading.Thread(target=_run_job, args=(job_id, prompt, out_dir),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return {"state": job["state"], "stage": job.get("stage"),
            "verdict": job.get("verdict"), "error": job.get("error"),
            "summary": job.get("summary"), "out_dir": job["out_dir"],
            "artifacts": {name: f"/artifact/{job_id}/{name}"
                          for name in (job.get("artifacts") or {})}}


@app.get("/artifact/{job_id}/{name}")
def artifact(job_id: str, name: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    if name not in ARTIFACT_NAMES:               # whitelist — no path traversal
        raise HTTPException(status_code=404,
                            detail=f"unknown artifact {name!r} "
                                   f"(one of {list(ARTIFACT_NAMES)})")
    path = Path(job["out_dir"]) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} not produced (yet)")
    return FileResponse(path, media_type=ARTIFACT_MEDIA_TYPES.get(name))


# Mounted last so /run, /status, /artifact win; html=True serves index.html at /.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
