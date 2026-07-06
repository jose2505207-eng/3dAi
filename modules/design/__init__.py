"""Module 1 — Design: natural-language prompt → Gemma → CadQuery → STEP/STL.

Public entry point: `run_design`. CLI: `python -m modules.design "<prompt>"`.
"""

from modules.design.loop import DesignError, RunRecord, run_design

__all__ = ["run_design", "RunRecord", "DesignError"]
