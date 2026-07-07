"""Module 2 — Simulation. Layer 1: deterministic checks (no solver yet).

Public entry point: `run_checks(run_dir)`. CLI: `python -m modules.simulation <run-dir>`.
"""

from modules.simulation.checks import RunDirError, run_checks

__all__ = ["run_checks", "RunDirError"]
