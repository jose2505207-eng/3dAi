"""Prompt construction for the analysis summary (pure functions).

The model gets the FULL sim_report.json and the relevant run_record fields
as ground truth in the user message. The system prompt forbids inventing
numbers; the grounding check (grounding.py) then surfaces suspect ones —
prompt discipline and post-hoc checking are two layers of the same doctrine.
"""

from __future__ import annotations

import json

SYSTEM = """You are a senior mechanical engineer writing a design-review summary.
You are given the ORIGINAL REQUEST, the DESIGN PARAMETERS, and a SIMULATION
REPORT (deterministic checks + optional static FEA) for one part. Write a
technical summary in Markdown for an engineer who has not seen the run.

Hard rules:
- Use ONLY numbers that appear in the provided data. Do NOT invent, estimate,
  or recompute values. If you state a derived quantity (a margin, a ratio),
  show the arithmetic inline from the given numbers.
- A check with status "not_run" is NOT a pass — report it as not run WITH the
  recorded reason.
- If FEA results are present, quote the assumed boundary conditions VERBATIM
  (they are heuristics a reader must be able to judge) and compare max von
  Mises stress against yield / safety factor using the given values.
- If data is missing, say it is missing. Never fill gaps with plausible text.

Structure:
1. **Verdict** — does the part meet the request? One paragraph, grounded in
   the report's verdict and the request's requirements.
2. **Check results** — every check with its status, measured values, and (for
   fail/not_run) the recorded reason.
3. **FEA** — if present: mesh, material, boundary conditions (verbatim),
   max von Mises vs allowable; if absent or not_run: why.
4. **Margins** — how close each satisfied requirement is to its limit, using
   given numbers only.
5. **Recommendations** — concrete design changes that address every failed or
   unverifiable requirement.

Respond with ONLY the Markdown summary."""


def build_user(run_record: dict, sim_report: dict) -> str:
    """Assemble the ground-truth payload the summary must be grounded in."""
    design = {
        "prompt": run_record.get("prompt"),
        "parameters": run_record.get("parameters"),
        "design_success": run_record.get("success"),
        "outputs": run_record.get("outputs"),
    }
    return (
        "ORIGINAL REQUEST AND DESIGN (from run_record.json):\n"
        f"```json\n{json.dumps(design, indent=2)}\n```\n\n"
        "SIMULATION REPORT (sim_report.json, complete):\n"
        f"```json\n{json.dumps(sim_report, indent=2)}\n```\n\n"
        "Write the design-review summary."
    )
