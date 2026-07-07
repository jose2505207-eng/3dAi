"""Layer 1: deterministic checks on a Module 1 run dir. No solver, no LLM.

Consumes ONLY Module 1's file outputs (part.step, run_record.json; part.stl
is hashed into provenance but unused by these checks) — never imports
modules.design. Output: a shared.schemas.SimReport.

Honesty rule (binding): every check is pass | fail | not_run. A check that
could not run — geometry unloadable, material unresolvable, no parameter to
compare against, capability not implemented in Layer 1 — is `not_run` with
the reason. Never `pass` by default, never a silent fallback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from modules.simulation.geometry import GeometryFacts, inspect_step
from modules.simulation.materials import UnknownMaterialError, resolve_material
from shared.schemas import (FAIL, NOT_RUN, PASS, CheckResult, SimReport,
                            file_provenance, utc_now)

# Parameter-name tokens that imply an OVERALL dimension of the part
# (matched against '_'-split name tokens: plate_l -> {plate, l}).
DIM_TOKENS = {"l", "w", "h", "len", "length", "width", "height",
              "t", "thick", "thickness", "depth"}
MAX_MASS_RE = re.compile(r"(max_?mass|mass_?limit|max_?weight)", re.I)
HOLE_NAME_RE = re.compile(r"(hole|bore)", re.I)

REL_TOL = 0.005  # 0.5 % — STEP round-trips are exact; this absorbs float noise
ABS_TOL = 0.01   # mm / g floor for tiny values


class RunDirError(Exception):
    """The run dir does not satisfy Module 1's output contract (config/IO)."""


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def _load_run_record(run_dir: Path) -> dict:
    path = run_dir / "run_record.json"
    if not path.exists():
        raise RunDirError(f"{path} not found — input must be a Module 1 run dir")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RunDirError(f"{path} is not valid JSON: {exc}") from exc


def check_geometry_valid(facts: GeometryFacts) -> CheckResult:
    """Mirror of Module 1's geometry gate, on the re-imported STEP."""
    if not facts.loaded:
        return CheckResult("geometry_valid", FAIL, reason=facts.error)
    value = {"solids": facts.solid_count, "volume_mm3": round(facts.volume_mm3, 3),
             "all_solids_valid": facts.all_solids_valid, "watertight": facts.watertight}
    problems = []
    if facts.solid_count < 1:
        problems.append("no solid body in the STEP")
    if facts.volume_mm3 <= 0:
        problems.append(f"total volume {facts.volume_mm3:.3f} mm^3 (must be > 0)")
    if not facts.all_solids_valid:
        problems.append("OCCT BRepCheck reports an invalid solid")
    if not facts.watertight:
        problems.append("not watertight (an open shell exists)")
    if problems:
        return CheckResult("geometry_valid", FAIL, value=value, reason="; ".join(problems))
    return CheckResult("geometry_valid", PASS, value=value)


def check_single_body(facts: GeometryFacts) -> CheckResult:
    if facts.solid_count == 1:
        return CheckResult("single_body", PASS, value={"solids": 1})
    return CheckResult("single_body", FAIL, value={"solids": facts.solid_count},
                       reason=f"STEP contains {facts.solid_count} solids — expected "
                              "exactly 1 connected body (disconnected unions are "
                              "unmanufacturable as one part)")


def check_bounding_box(facts: GeometryFacts, parameters: dict) -> CheckResult:
    """Report the bbox; compare against run_record parameters whose names
    imply overall dimensions. A parameter smaller than the bbox may be an
    interior dimension, so an unmatched-but-plausible set is `not_run`
    (inconclusive), not a fake pass/fail; a dimension EXCEEDING the bbox is
    a definite fail."""
    expected = {name: v for name, v in parameters.items()
                if isinstance(v, (int, float)) and v > 0
                and set(name.lower().split("_")) & DIM_TOKENS}
    value: dict = {"bbox_mm": facts.bbox_mm, "expected_from_parameters": expected}
    if not expected:
        return CheckResult("bounding_box", NOT_RUN, value=value,
                           reason="run_record parameters name no overall dimension "
                                  f"(recognized tokens: {sorted(DIM_TOKENS)}); "
                                  f"measured bbox {facts.bbox_mm} mm reported only")
    matches = {name: any(_close(v, axis) for axis in facts.bbox_mm)
               for name, v in expected.items()}
    value["matched"] = matches
    oversized = {n: v for n, v in expected.items()
                 if v > max(facts.bbox_mm) * (1 + REL_TOL) + ABS_TOL}
    if oversized:
        return CheckResult("bounding_box", FAIL, value=value,
                           reason=f"parameter(s) exceed the measured bbox "
                                  f"{facts.bbox_mm} mm: {oversized}")
    if all(matches.values()):
        return CheckResult("bounding_box", PASS, value=value)
    unmatched = {n: expected[n] for n, ok in matches.items() if not ok}
    return CheckResult("bounding_box", NOT_RUN, value=value,
                       reason=f"parameter(s) {unmatched} match no bbox axis of "
                              f"{facts.bbox_mm} mm but fit inside it — inconclusive "
                              "(interior dimensions?); not asserting pass or fail")


def check_mass_budget(facts: GeometryFacts, parameters: dict) -> tuple[CheckResult, dict | None]:
    """Mass = volume * density. Returns (check, material-used-or-None).
    Comparison against max_mass is binding only when MATERIAL is explicit
    config; a default-assumption density makes it `not_run` per the honesty
    rule. Mass limit unit is grams (Module 1 parameters are unit-naked;
    assumption recorded in the reason)."""
    volume_cm3 = facts.volume_mm3 / 1000.0
    value: dict = {"volume_cm3": round(volume_cm3, 4)}
    try:
        material = resolve_material()
    except UnknownMaterialError as exc:
        return CheckResult("mass_budget", NOT_RUN, value=value,
                           reason=f"cannot compute mass: {exc}"), None

    mass_g = volume_cm3 * material["density_g_cm3"]
    value.update(mass_g=round(mass_g, 3), material=material["name"],
                 density_g_cm3=material["density_g_cm3"],
                 density_source=material["source"])

    limits = {n: v for n, v in parameters.items()
              if isinstance(v, (int, float)) and MAX_MASS_RE.search(n)}
    if not limits:
        return CheckResult(
            "mass_budget", NOT_RUN, value=value,
            reason=f"computed mass {mass_g:.1f} g ({material['name']}, "
                   f"{material['density_g_cm3']} g/cm^3, {material['source']}) but "
                   "run_record parameters carry no max_mass/mass_limit to compare"), material

    limit_name, limit_g = next(iter(limits.items()))
    value.update(limit_parameter=limit_name, max_mass_g=limit_g)
    if material["source"] == "default_assumption":
        return CheckResult(
            "mass_budget", NOT_RUN, value=value,
            reason=f"assumption-based: MATERIAL is not set, so density is the "
                   f"default assumption {material['name']}={material['density_g_cm3']} "
                   f"g/cm^3. Indicative only: mass {mass_g:.1f} g vs {limit_name}="
                   f"{limit_g} g (grams assumed). Set MATERIAL to make this check "
                   "binding"), material

    if mass_g <= limit_g + ABS_TOL:
        return CheckResult("mass_budget", PASS, value=value), material
    return CheckResult("mass_budget", FAIL, value=value,
                       reason=f"mass {mass_g:.1f} g exceeds {limit_name}={limit_g} g "
                              f"({material['name']}, {material['density_g_cm3']} "
                              "g/cm^3 from MATERIAL; grams assumed)"), material


def check_min_wall_thickness(facts: GeometryFacts) -> CheckResult:
    """Not implemented in Layer 1 — honest not_run, never a fake pass."""
    return CheckResult(
        "min_wall_thickness", NOT_RUN,
        reason="not implemented in Layer 1: a robust minimum-wall measurement "
               "needs medial-axis/offset analysis (or FEA-adjacent meshing) that "
               "deterministic STEP inspection does not provide; refusing to "
               "approximate it from the bounding box")


def check_hole_geometry(facts: GeometryFacts, parameters: dict) -> CheckResult:
    """Best-effort: cylindrical faces in the STEP vs hole-diameter parameters.
    Layer 1 cannot distinguish holes from bosses (concavity not analyzed) —
    stated in the evidence rather than hidden."""
    observed_d = sorted({round(2 * r, 3) for r in facts.cylindrical_face_radii_mm})
    value: dict = {"cylindrical_faces": len(facts.cylindrical_face_radii_mm),
                   "observed_diameters_mm": observed_d,
                   "note": "concave/convex not distinguished — bosses count too"}

    expected: dict[str, float] = {}
    for name, v in parameters.items():
        if not isinstance(v, (int, float)) or v <= 0 or not HOLE_NAME_RE.search(name):
            continue
        lname = name.lower()
        if lname.endswith(("_r", "_rad", "_radius")) or "radius" in lname:
            expected[name] = 2 * v
        elif lname.endswith(("_d", "_dia", "_diam", "_diameter")) or "diam" in lname:
            expected[name] = v
    value["expected_diameters_mm"] = expected

    if not expected:
        return CheckResult("hole_geometry", NOT_RUN, value=value,
                           reason="run_record parameters name no hole diameter/radius; "
                                  f"observed {len(observed_d)} distinct cylindrical "
                                  f"diameter(s) {observed_d} mm reported only")
    missing = {n: d for n, d in expected.items()
               if not any(_close(d, od) for od in observed_d)}
    if missing:
        return CheckResult("hole_geometry", FAIL, value=value,
                           reason=f"expected hole diameter(s) {missing} mm not found "
                                  f"among cylindrical faces {observed_d} mm")
    return CheckResult("hole_geometry", PASS, value=value)


def _not_run_all(names: list[str], reason: str) -> list[CheckResult]:
    return [CheckResult(name, NOT_RUN, reason=reason) for name in names]


def run_checks(run_dir: Path) -> SimReport:
    """Run all Layer 1 checks on a Module 1 run dir. Raises RunDirError for
    contract violations (missing dir/inputs) — everything else is an honest
    check outcome inside the report."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise RunDirError(f"{run_dir} is not a directory")
    step_path = run_dir / "part.step"
    if not step_path.exists():
        raise RunDirError(f"{step_path} not found — input must be a Module 1 run dir")
    run_record = _load_run_record(run_dir)
    parameters = run_record.get("parameters") or {}

    facts = inspect_step(step_path)
    checks = [check_geometry_valid(facts)]
    material = None
    if facts.loaded:
        checks.append(check_single_body(facts))
        checks.append(check_bounding_box(facts, parameters))
        mass_check, material = check_mass_budget(facts, parameters)
        checks.append(mass_check)
        checks.append(check_min_wall_thickness(facts))
        checks.append(check_hole_geometry(facts, parameters))
    else:
        checks += _not_run_all(
            ["single_body", "bounding_box", "mass_budget",
             "min_wall_thickness", "hole_geometry"],
            f"geometry could not be loaded: {facts.error}")

    stl_prov = file_provenance(run_dir / "part.stl")
    provenance = {
        "module": "modules.simulation", "layer": 1, "timestamp": utc_now(),
        "run_dir": str(run_dir),
        "inputs": {"part.step": file_provenance(step_path),
                   "run_record.json": file_provenance(run_dir / "run_record.json"),
                   "part.stl": stl_prov},
        "design": {k: run_record.get(k) for k in ("prompt", "model", "endpoint", "success")},
    }
    if stl_prov is None:
        provenance["notes"] = ("part.stl missing from the run dir — unused by "
                               "Layer 1 checks but a Module 1 contract violation")

    return SimReport(verdict=SimReport.verdict_of(checks), checks=checks,
                     material=material, provenance=provenance)
