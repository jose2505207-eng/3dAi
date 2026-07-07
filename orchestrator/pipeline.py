"""Chains the three modules: prompt → design → simulation → analysis.

Honest about partial failure: a design failure STOPS the run (there is no
geometry to simulate); a simulation contract violation stops before analysis;
an analysis/LLM failure is recorded but the design+sim artifacts are kept.
Analysis ALWAYS runs when a sim report exists — even on a fail/incomplete
verdict, because explaining failures is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from modules.analysis.analyze import (SUMMARY_FILENAME, AnalysisError,
                                      AnalysisInputError, run_analysis)
from modules.design.loop import DesignError, run_design
from modules.simulation.checks import RunDirError, run_checks
from shared.llm import LLMClient
from shared.schemas import SIM_REPORT_FILENAME

ARTIFACT_NAMES = ("part.step", "part.stl", SIM_REPORT_FILENAME, SUMMARY_FILENAME)
STAGES = ("design", "simulation", "analysis")


@dataclass
class PipelineResult:
    out_dir: str
    ok: bool                      # every stage succeeded
    stage: str                    # last stage reached
    stages: dict = field(default_factory=dict)   # name -> {ok, error}
    verdict: str | None = None    # sim verdict (pass|fail|incomplete), if reached
    artifacts: dict = field(default_factory=dict)  # name -> path, existing files only
    summary: str | None = None    # analysis.md text, if produced

    def to_dict(self) -> dict:
        return {"out_dir": self.out_dir, "ok": self.ok, "stage": self.stage,
                "stages": self.stages, "verdict": self.verdict,
                "artifacts": self.artifacts, "summary": self.summary}


def _artifacts(out_dir: Path) -> dict:
    return {name: str(out_dir / name)
            for name in ARTIFACT_NAMES if (out_dir / name).exists()}


def run_pipeline(prompt: str, out_dir: Path, client: LLMClient, *,
                 max_iterations: int | None = None, with_fea: bool = True,
                 on_stage: Callable[[str], None] | None = None) -> PipelineResult:
    """Run design → simulation → analysis into `out_dir`. Never raises for a
    stage failure — the failure and its real evidence live in the result.
    `on_stage` (if given) is called with each stage name as it starts."""
    out_dir = Path(out_dir)
    result = PipelineResult(out_dir=str(out_dir), ok=False, stage="design")

    def _start(stage: str) -> None:
        result.stage = stage
        if on_stage:
            on_stage(stage)

    def _fail(stage: str, error: str) -> PipelineResult:
        result.stages[stage] = {"ok": False, "error": error}
        result.artifacts = _artifacts(out_dir)
        return result

    _start("design")
    try:
        run_design(prompt, out_dir, client=client, max_iterations=max_iterations)
    except DesignError as exc:
        return _fail("design", str(exc))
    result.stages["design"] = {"ok": True, "error": None}

    _start("simulation")
    try:
        report = run_checks(out_dir, with_fea=with_fea)
    except RunDirError as exc:
        return _fail("simulation", str(exc))
    report.write(out_dir / SIM_REPORT_FILENAME)
    result.stages["simulation"] = {"ok": True, "error": None}
    result.verdict = report.verdict

    # ALWAYS attempt analysis once a sim report exists — a fail/incomplete
    # verdict is exactly what the summary must explain.
    _start("analysis")
    try:
        record = run_analysis(out_dir, client)
    except (AnalysisError, AnalysisInputError) as exc:
        return _fail("analysis", str(exc))
    result.stages["analysis"] = {"ok": True, "error": None}
    result.summary = Path(record.summary_path).read_text()

    result.ok = True
    result.artifacts = _artifacts(out_dir)
    return result
