"""Sandboxed execution of model-generated CadQuery scripts.

Model output is untrusted. Before execution the script is statically
validated by AST walk (import whitelist, forbidden builtins, no dunder
attribute access), then run in a separate `python -I` process with a hard
timeout and a scratch cwd. This guards against a misbehaving model, not a
hostile local user.

Geometry validation happens inside the subprocess (runner.py) because it
needs the OCCT kernel; this module turns the runner's JSON verdicts into
either a GeometryReport or a CADScriptError whose message is real feedback
for the model (traceback tail, or the failing validation numbers).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ALLOWED_IMPORTS = {"cadquery", "math", "numpy"}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview",
    "exit", "quit", "help",
}

RUNNER = Path(__file__).parent / "runner.py"


class CADScriptError(Exception):
    """Validation or execution failure; the message is fed back to the model.
    `phase` says which gate failed: safety | execution | validation."""

    def __init__(self, phase: str, message: str):
        super().__init__(message)
        self.phase = phase


@dataclass
class GeometryReport:
    volume_mm3: float
    bbox_mm: list[float]
    solid_count: int
    is_valid_solid: bool
    is_closed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def validate_script(code: str) -> list[str]:
    """Static safety check. Returns violations; empty list = OK to run."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    violations.append(f"import of '{alias.name}' not allowed "
                                      f"(whitelist: {sorted(ALLOWED_IMPORTS)})")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                violations.append(f"import from '{node.module}' not allowed")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.append(f"use of '{node.id}' not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            violations.append(f"dunder attribute access '{node.attr}' not allowed")
    return violations


def run_script(code: str, step_path: Path, stl_path: Path,
               timeout_s: float = 120.0) -> GeometryReport:
    """Validate then execute the script in an isolated subprocess; judge the
    geometry verdicts. Raises CADScriptError with model-feedable text."""
    violations = validate_script(code)
    if violations:
        raise CADScriptError("safety",
                             "script rejected by safety validator: " + "; ".join(violations))

    # Absolute paths: the subprocess runs with cwd=tempdir, so relative
    # outputs would land in the tempdir and vanish with it.
    step_path, stl_path = step_path.resolve(), stl_path.resolve()
    step_path.parent.mkdir(parents=True, exist_ok=True)
    stl_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cad-sandbox-") as tmp:
        script_file = Path(tmp) / "cad_script.py"
        script_file.write_text(code)
        cmd = [sys.executable, "-I", str(RUNNER),
               str(script_file), str(step_path), str(stl_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout_s, cwd=tmp)
        except subprocess.TimeoutExpired as exc:
            raise CADScriptError(
                "execution",
                f"CAD script exceeded the {timeout_s:.0f}s timeout — simplify the "
                "geometry") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "no output").strip().splitlines()[-12:]
        raise CADScriptError("execution", "CAD script failed:\n" + "\n".join(tail))

    try:
        metrics = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise CADScriptError("execution",
                             f"runner produced no metrics: {proc.stdout[-300:]!r}") from exc

    report = GeometryReport(**metrics)
    problems: list[str] = []
    if report.solid_count < 1:
        problems.append("the result contains no solid body")
    if report.volume_mm3 <= 0:
        problems.append(f"solid volume is {report.volume_mm3:.3f} mm^3 (must be > 0)")
    if not report.is_valid_solid:
        problems.append("OCCT BRepCheck reports the solid as INVALID")
    if not report.is_closed:
        problems.append("the solid is not watertight (an open shell exists)")
    if problems:
        raise CADScriptError(
            "validation",
            "geometry validation failed: " + "; ".join(problems)
            + f". Metrics: volume={report.volume_mm3:.1f} mm^3, bbox="
            + "x".join(f"{b:.1f}" for b in report.bbox_mm)
            + f" mm, solids={report.solid_count}")

    if not step_path.exists() or step_path.stat().st_size == 0:
        raise CADScriptError("validation", "script ran but produced no usable STEP file")
    if not stl_path.exists() or stl_path.stat().st_size <= 84:
        raise CADScriptError("validation", "script ran but produced no usable STL file")
    return report
