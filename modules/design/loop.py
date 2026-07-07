"""The self-correction loop: prompt → generate → execute → validate → retry.

    Gemma writes a CadQuery script
      -> AST safety validation      (fail -> real violations, retry)
      -> sandboxed build            (fail -> real traceback tail, retry)
      -> geometry validation        (fail -> real metrics, retry)
      -> valid watertight solid     -> STEP + STL + script + run record

Budget: CAD_MAX_ITERATIONS (default 5). An LLM-call failure is NOT retried
inside the loop — it is surfaced immediately with the real HTTP evidence
(no-silent-fallback doctrine, wiki/pages/infra-gemma-vllm-amd.md). The run
record keeps per-iteration provenance (endpoint, model, response id, tokens)
so a template/stub answer can never masquerade as a real Gemma run.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from modules.design import prompts
from modules.design.sandbox import (CADScriptError, GeometryReport,
                                    extract_parameters, run_script)
from shared.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 5


class DesignError(Exception):
    """The run could not produce a valid solid; the run record (attached as
    `.record`) holds the full per-iteration evidence."""

    def __init__(self, message: str, record: "RunRecord"):
        super().__init__(message)
        self.record = record


@dataclass
class Iteration:
    n: int
    llm: dict            # CallRecord.to_dict() — real-call provenance
    phase: str           # llm | safety | execution | validation | ok
    passed: bool
    error: str | None = None
    geometry: dict | None = None

    def to_dict(self) -> dict:
        return {"n": self.n, "llm": self.llm, "phase": self.phase,
                "passed": self.passed, "error": self.error, "geometry": self.geometry}


@dataclass
class RunRecord:
    prompt: str
    model: str
    endpoint: str
    max_iterations: int
    started: str
    preflight: dict | None = None
    iterations: list[Iteration] = field(default_factory=list)
    success: bool = False
    failure: str | None = None
    finished: str | None = None
    parameters: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt, "model": self.model, "endpoint": self.endpoint,
            "max_iterations": self.max_iterations, "started": self.started,
            "finished": self.finished, "preflight": self.preflight,
            "success": self.success, "failure": self.failure,
            "iterations": [it.to_dict() for it in self.iterations],
            "parameters": self.parameters, "outputs": self.outputs,
        }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run_design(description: str, out_dir: Path, client: LLMClient | None = None,
               max_iterations: int | None = None,
               cad_timeout_s: float = 120.0,
               on_iteration: Callable[[int, int, str, str | None], None] | None = None,
               ) -> RunRecord:
    """Run the full loop. Returns a successful RunRecord (STEP/STL/script/
    record written under out_dir) or raises DesignError carrying the record.

    `client` needs `.model`, `.base_url`, `.preflight()` and `.chat()` — tests
    inject a fake; production uses shared.llm.LLMClient.from_env().

    `on_iteration(attempt, budget, phase, error)` (optional) surfaces live
    progress to a caller mid-loop — the iteration records are otherwise
    invisible until the final return / run_record.json. Called at attempt
    start (phase "llm", error None) and after each iteration outcome
    (phase llm|safety|execution|validation with the real error, or "ok").
    """
    client = client or LLMClient.from_env()
    budget = max_iterations or int(os.environ.get("CAD_MAX_ITERATIONS",
                                                  DEFAULT_MAX_ITERATIONS))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    step_path, stl_path = out_dir / "part.step", out_dir / "part.stl"

    record = RunRecord(prompt=description, model=client.model,
                       endpoint=client.base_url, max_iterations=budget,
                       started=_now())

    def _finish_failed(msg: str) -> DesignError:
        record.success, record.failure, record.finished = False, msg, _now()
        _write_record(record, out_dir)
        return DesignError(msg, record)

    # PREFLIGHT: refuse to loop against an endpoint that isn't a live
    # OpenAI-compatible API (unreachable, or a content filter answering HTML).
    try:
        models = client.preflight()
        record.preflight = {"ok": True, "url": f"{client.base_url}/models",
                            "models": [m.get("id") for m in models.get("data", [])]}
    except LLMError as exc:
        record.preflight = {"ok": False, "url": f"{client.base_url}/models",
                            "error": str(exc)}
        raise _finish_failed(f"preflight failed: {exc}") from exc

    def _notify(attempt: int, phase: str, error: str | None) -> None:
        if on_iteration:
            on_iteration(attempt, budget, phase, error)

    script, feedback = "", ""
    for attempt in range(1, budget + 1):
        user = (prompts.initial_prompt(description) if not feedback
                else prompts.retry_prompt(description, script, feedback))
        logger.info("iteration %d/%d: asking %s for a CadQuery script",
                    attempt, budget, client.model)
        _notify(attempt, "llm", None)
        try:
            text, call = client.chat(prompts.SYSTEM, user)
        except LLMError as exc:
            call = getattr(exc, "call_record", None)
            record.iterations.append(Iteration(
                n=attempt, llm=call.to_dict() if call else {"called": True, "error": str(exc)},
                phase="llm", passed=False, error=str(exc)))
            _notify(attempt, "llm", str(exc))
            raise _finish_failed(f"LLM call failed on iteration {attempt}: {exc}") from exc

        script = prompts.extract_code(text)
        try:
            report: GeometryReport = run_script(script, step_path, stl_path,
                                                timeout_s=cad_timeout_s)
        except CADScriptError as exc:
            feedback = str(exc)
            record.iterations.append(Iteration(
                n=attempt, llm=call.to_dict(), phase=exc.phase,
                passed=False, error=feedback))
            logger.warning("iteration %d failed (%s): %s",
                           attempt, exc.phase, feedback.splitlines()[0][:120])
            _notify(attempt, exc.phase, feedback)
            continue

        record.iterations.append(Iteration(
            n=attempt, llm=call.to_dict(), phase="ok", passed=True,
            geometry=report.to_dict()))
        _notify(attempt, "ok", None)
        record.success, record.finished = True, _now()
        record.parameters = extract_parameters(script)
        script_path = out_dir / "part.py"
        script_path.write_text(script + "\n")
        record.outputs = {"step": str(step_path), "stl": str(stl_path),
                          "script": str(script_path),
                          "record": str(out_dir / "run_record.json")}
        _write_record(record, out_dir)
        logger.info("converged on iteration %d/%d (volume %.1f mm^3)",
                    attempt, budget, report.volume_mm3)
        return record

    raise _finish_failed(
        f"iteration budget ({budget}) exhausted without a valid solid; "
        f"last error: {feedback.splitlines()[0][:200] if feedback else 'n/a'}")


def _write_record(record: RunRecord, out_dir: Path) -> None:
    (out_dir / "run_record.json").write_text(
        json.dumps(record.to_dict(), indent=2) + "\n")
