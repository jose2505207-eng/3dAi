"""Shared fixtures: a passing and a failing Module 1+2 run dir on disk, and a
fake LLM client mimicking shared.llm.LLMClient's surface (.model, .base_url,
.preflight(), .chat()) so the module is tested end to end without a network.
"""

import copy
import json

import pytest

from shared.llm import CallRecord

RUN_RECORD = {
    "prompt": "a mounting bracket that holds 500 N with a safety factor of 2, under 200 g",
    "model": "google/gemma-3-27b-it",
    "endpoint": "http://fake:8000/v1",
    "success": True,
    "parameters": {"base_length": 60.0, "base_width": 40.0,
                   "base_thickness": 5.0, "hole_diameter": 6.0},
    "outputs": {"step": "part.step", "stl": "part.stl"},
}

SIM_REPORT_PASS = {
    "schema": "sim_report/v1",
    "verdict": "pass",
    "material": {"name": "aluminum_6061", "density_g_cm3": 2.7, "e_mpa": 68900,
                 "nu": 0.33, "yield_mpa": 276, "source": "env"},
    "checks": [
        {"name": "geometry_valid", "status": "pass",
         "value": {"solids": 1, "volume_mm3": 12000.0, "watertight": True},
         "reason": None},
        {"name": "single_body", "status": "pass", "value": {"solids": 1},
         "reason": None},
        {"name": "mass_budget", "status": "pass",
         "value": {"mass_g": 32.4, "max_mass_g": 200}, "reason": None},
        {"name": "fea_static", "status": "pass",
         "value": {"max_von_mises_mpa": 41.3, "allowable_mpa": 138.0,
                   "safety_factor": 2.0},
         "reason": None},
    ],
    "fea": {
        "mesh": {"nodes": 2970, "elements": 1406, "element_type": "C3D10"},
        "boundary_conditions": {
            "heuristic": "lowest-Z hole group fixed (all DOFs); highest-Z "
                         "large planar face loaded -Z"},
        "results": {"max_von_mises_mpa": 41.3, "max_displacement_mm": 0.021},
    },
    "provenance": {"module": "modules.simulation", "layer": 1},
}

SIM_REPORT_FAIL = {
    "schema": "sim_report/v1",
    "verdict": "fail",
    "material": {"name": "aluminum_6061", "density_g_cm3": 2.7, "e_mpa": 68900,
                 "nu": 0.33, "yield_mpa": 276, "source": "default_assumption"},
    "checks": [
        {"name": "geometry_valid", "status": "pass",
         "value": {"solids": 1, "volume_mm3": 174227.7, "watertight": True},
         "reason": None},
        {"name": "mass_budget", "status": "fail",
         "value": {"mass_g": 470.4, "max_mass_g": 200},
         "reason": "mass 470.4 g exceeds max_mass=200 g"},
        {"name": "fea_static", "status": "not_run", "value": None,
         "reason": "solver failed: ccx nonpositive jacobian in element 5163"},
    ],
    "fea": None,
    "provenance": {"module": "modules.simulation", "layer": 1},
}

# Every numeric token here exists in RUN_RECORD/SIM_REPORT_PASS — a clean,
# fully grounded summary. The ordered list exercises the list-marker skip.
CLEAN_REPLY = """# Design review

**Verdict:** the bracket meets the request — it holds 500 N with a safety
factor of 2 and its mass of 32.4 g is under the 200 g budget.

1. geometry_valid: pass (1 solid, volume 12000.0 mm^3, watertight)
2. mass_budget: pass (32.4 g vs the 200 g limit)
3. fea_static: pass

FEA: max von Mises 41.3 MPa vs allowable 138.0 MPa (yield 276 MPa at the
requested safety factor of 2). BCs assumed: "lowest-Z hole group fixed (all
DOFs); highest-Z large planar face loaded -Z" — review before trusting.

Recommendation: none required; all checks passed.
"""

FABRICATED_REPLY = CLEAN_REPLY + (
    "\nThe design therefore achieves an actual safety factor of 9.7.\n")


class FakeClient:
    base_url = "http://fake:8000/v1"
    model = "google/gemma-3-27b-it"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts_seen = []

    def preflight(self):
        return {"data": [{"id": self.model}]}

    def chat(self, system, user, temperature=0.4):
        self.prompts_seen.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        record = CallRecord(called=True, endpoint=f"{self.base_url}/chat/completions",
                            model=self.model, http_status=200,
                            response_id=f"fake-{len(self.prompts_seen)}",
                            latency_s=0.01)
        return reply, record


@pytest.fixture
def make_run_dir(tmp_path):
    """Write run_record.json + sim_report.json fixtures into a fresh dir."""
    def _make(sim_report=SIM_REPORT_PASS, run_record=RUN_RECORD,
              omit=()):
        for name, data in (("run_record.json", run_record),
                           ("sim_report.json", sim_report)):
            if name in omit:
                continue
            (tmp_path / name).write_text(json.dumps(copy.deepcopy(data), indent=2))
        return tmp_path
    return _make
