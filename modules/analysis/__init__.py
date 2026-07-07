"""Module 3 — Analysis. Gemma writes a grounded technical summary of a
Module 1+2 run dir.

Public entry point: `run_analysis(run_dir, client)`.
CLI: `python -m modules.analysis <run-dir> [--strict]`.
"""

from modules.analysis.analyze import (AnalysisError, AnalysisInputError,
                                      AnalysisRecord, run_analysis)

__all__ = ["run_analysis", "AnalysisRecord", "AnalysisError", "AnalysisInputError"]
