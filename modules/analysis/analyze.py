"""Module 3 core: run dir (run_record.json + sim_report.json) → analysis.md
+ analysis_record.json, via the shared provider layer.

Refuses half-run dirs — a summary is never fabricated from partial inputs.
LLM failures surface the real evidence (shared.llm doctrine) and the failure
record is still written for audit. The numeric grounding check warns by
default (see grounding.py for why it is only a heuristic).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from modules.analysis import prompts
from modules.analysis.grounding import allowed_numbers, flag_ungrounded
from shared.llm import LLMClient, LLMError
from shared.schemas import (SIM_REPORT_FILENAME, SIM_REPORT_SCHEMA,
                            file_provenance, utc_now)

SUMMARY_FILENAME = "analysis.md"
RECORD_FILENAME = "analysis_record.json"

GROUNDING_NOTE = ("heuristic: flags summary numbers absent from the inputs "
                  "(~1% tolerance); surfaces suspects, does not prove absence "
                  "of fabrication")


class AnalysisInputError(Exception):
    """The run dir does not satisfy the Module 1+2 output contract."""


class AnalysisError(Exception):
    """The analysis could not be produced; `.record` holds the evidence."""

    def __init__(self, message: str, record: "AnalysisRecord"):
        super().__init__(message)
        self.record = record


@dataclass
class AnalysisRecord:
    started: str
    inputs: list = field(default_factory=list)   # {path, sha256, bytes} per consumed file
    preflight: dict | None = None
    call_record: dict | None = None              # CallRecord.to_dict()
    grounding: dict | None = None                # {allowed_numbers_count, flagged, note}
    summary_path: str | None = None
    success: bool = False
    failure: str | None = None
    finished: str | None = None

    def to_dict(self) -> dict:
        return {"started": self.started, "finished": self.finished,
                "success": self.success, "failure": self.failure,
                "inputs": self.inputs, "preflight": self.preflight,
                "call_record": self.call_record, "grounding": self.grounding,
                "summary_path": self.summary_path}


def load_inputs(run_dir: Path) -> tuple[dict, dict]:
    """Read and validate the two consumed files. Raises AnalysisInputError —
    never fabricates a summary from a half-run dir."""
    run_dir = Path(run_dir)
    loaded = []
    for name, label in ((("run_record.json"), "Module 1 run record"),
                        ((SIM_REPORT_FILENAME), "Module 2 sim report")):
        path = run_dir / name
        if not path.exists():
            raise AnalysisInputError(
                f"{path} not found — refusing to summarize a half-run dir "
                f"(need both run_record.json and {SIM_REPORT_FILENAME})")
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise AnalysisInputError(f"{path} is not readable JSON ({label}): {exc}") from exc
        if not isinstance(data, dict):
            raise AnalysisInputError(f"{path} is not a JSON object ({label})")
        loaded.append(data)
    run_record, sim_report = loaded
    schema = sim_report.get("schema")
    if schema != SIM_REPORT_SCHEMA:
        raise AnalysisInputError(
            f"{run_dir / SIM_REPORT_FILENAME} has schema {schema!r}, "
            f"expected {SIM_REPORT_SCHEMA!r}")
    return run_record, sim_report


def run_analysis(run_dir: Path, client: LLMClient, *, temperature: float = 0.3,
                 strict: bool = False) -> AnalysisRecord:
    """Produce analysis.md + analysis_record.json in `run_dir`. Returns the
    record; raises AnalysisInputError (bad inputs, nothing written) or
    AnalysisError (LLM failure — failure record written and attached).

    `client` needs `.model`, `.base_url`, `.preflight()` and `.chat()` — tests
    inject a fake; production uses shared.llm.LLMClient.from_env(). `strict`
    is recorded in the grounding block; exit-code policy is the CLI's.
    """
    run_dir = Path(run_dir)
    run_record, sim_report = load_inputs(run_dir)

    record = AnalysisRecord(
        started=utc_now(),
        inputs=[file_provenance(run_dir / "run_record.json"),
                file_provenance(run_dir / SIM_REPORT_FILENAME)])

    def _finish_failed(msg: str) -> AnalysisError:
        record.success, record.failure, record.finished = False, msg, utc_now()
        _write_record(record, run_dir)
        return AnalysisError(msg, record)

    try:
        models = client.preflight()
        record.preflight = {"ok": True, "url": f"{client.base_url}/models",
                            "models": [m.get("id") for m in models.get("data", [])]}
    except LLMError as exc:
        record.preflight = {"ok": False, "url": f"{client.base_url}/models",
                            "error": str(exc)}
        raise _finish_failed(f"preflight failed: {exc}") from exc

    try:
        text, call = client.chat(prompts.SYSTEM,
                                 prompts.build_user(run_record, sim_report),
                                 temperature=temperature)
    except LLMError as exc:
        call = getattr(exc, "call_record", None)
        record.call_record = call.to_dict() if call else None
        raise _finish_failed(f"LLM call failed: {exc}") from exc
    record.call_record = call.to_dict()

    if not text.strip():
        raise _finish_failed("model returned an empty summary")

    summary_path = run_dir / SUMMARY_FILENAME
    summary_path.write_text(text.strip() + "\n")
    record.summary_path = str(summary_path)

    allowed = allowed_numbers(run_record, sim_report)
    flagged = flag_ungrounded(text, allowed)
    record.grounding = {"allowed_numbers_count": len(allowed),
                        "flagged": flagged, "strict": strict,
                        "note": GROUNDING_NOTE}
    if flagged:
        print(f"grounding warning: {len(flagged)} number(s) in {summary_path} "
              f"not found in the inputs (suspect, not proven wrong): {flagged}",
              file=sys.stderr)

    record.success, record.finished = True, utc_now()
    _write_record(record, run_dir)
    return record


def _write_record(record: AnalysisRecord, run_dir: Path) -> None:
    (run_dir / RECORD_FILENAME).write_text(
        json.dumps(record.to_dict(), indent=2) + "\n")
