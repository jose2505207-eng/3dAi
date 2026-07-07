"""Layer 2: static FEA (gmsh mesh → CalculiX solve → von Mises verdict).

BOUNDARY-CONDITION HEURISTIC (documented, and recorded verbatim in the
report so a human can audit it — deriving BCs automatically is hard and
this is an explicit approximation, not ground truth):

  * FIXED: the lowest-Z group of cylindrical faces — hole faces whose
    centroid Z is within 10% of part height of the lowest hole centroid.
    Reading: "the mounting holes are the bolted ones nearest the base."
    All DOFs of all their nodes are constrained.
  * LOAD: total force applied straight down (-Z assumption) on the highest-Z
    planar face with area >= 5% of the bbox footprint — "the load plate".
    Distributed as consistent nodal loads for a uniform traction on TRI6
    faces (midside nodes carry A/3 each, corners zero). Shares landing on
    fixed nodes would vanish into reactions, so they are excluded and the
    remainder rescaled to keep the applied total exact (recorded).
  * LOAD MAGNITUDE: a run_record parameter named like load/force (grams of
    the mass check don't apply here), else "<number> N" parsed from the
    design prompt; its source is recorded. No magnitude -> FEA not_run.

Anything unresolvable raises BCUnresolvable and the FEA check is not_run
with the reason — never a pass built on missing boundary conditions.
"""

from __future__ import annotations

import re
from pathlib import Path

from modules.simulation.ccx import (BCSpec, FixedSet, SolverError, find_ccx,
                                    parse_frd, run_ccx, write_deck)
from modules.simulation.ccx import INSTALL_HINT
from modules.simulation.mesher import (MeshData, MeshError, SurfaceInfo,
                                       _tri_area, mesh_step)
from shared.schemas import FAIL, NOT_RUN, PASS, CheckResult

LOAD_PARAM_RE = re.compile(r"(load|force)", re.I)
LOAD_PROMPT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*N\b")
SF_PARAM_RE = re.compile(r"(safety_?factor|^sf$|^fos$)", re.I)
SF_PROMPT_RE = re.compile(r"safety\s+factor\s+of\s+(\d+(?:\.\d+)?)", re.I)

DEFAULT_SAFETY_FACTOR = 2.0
HOLE_GROUP_TOL = 0.10   # holes within 10% of part height of the lowest group
LOAD_FACE_MIN_AREA = 0.05  # of the bbox footprint


class BCUnresolvable(Exception):
    """The heuristic could not derive boundary conditions; reason inside."""


def consistent_face_loads(mesh: MeshData, face: SurfaceInfo, total_force_n: float,
                          dof: int, exclude: set[int] = frozenset()
                          ) -> tuple[list[tuple[int, int, float]], float]:
    """Consistent nodal loads for a uniform traction on a TRI6-meshed face:
    each triangle's midside nodes carry area/3, corners zero. Shares on
    excluded (fixed) nodes would vanish into reactions, so they are dropped
    and the rest rescaled to keep the applied total exact. Returns
    (cloads, fraction_of_face_area_excluded)."""
    shares: dict[int, float] = {}
    for tri in face.tri6:
        a3 = _tri_area(*(mesh.nodes[t] for t in tri[:3])) / 3.0
        for mid in tri[3:6]:
            shares[mid] = shares.get(mid, 0.0) + a3
    live = {n: a for n, a in shares.items() if n not in exclude}
    if not live:
        raise BCUnresolvable("every load-face node is also fixed — load and "
                             "constraint regions coincide")
    excluded_fraction = 1.0 - sum(live.values()) / sum(shares.values())
    scale = total_force_n / sum(live.values())
    return [(n, dof, a * scale) for n, a in sorted(live.items())], excluded_fraction


def resolve_load_n(parameters: dict, prompt: str) -> tuple[float, str]:
    for name, v in parameters.items():
        if isinstance(v, (int, float)) and v > 0 and LOAD_PARAM_RE.search(name):
            return float(v), f"run_record parameter '{name}' (newtons assumed)"
    m = LOAD_PROMPT_RE.search(prompt or "")
    if m:
        return float(m.group(1)), f"parsed '{m.group(0)}' from the design prompt"
    raise BCUnresolvable(
        "no load magnitude: run_record has no load/force-named parameter and "
        "the prompt contains no '<number> N'")


def resolve_safety_factor(parameters: dict, prompt: str) -> tuple[float, str]:
    for name, v in parameters.items():
        if isinstance(v, (int, float)) and v > 0 and SF_PARAM_RE.search(name):
            return float(v), f"run_record parameter '{name}'"
    m = SF_PROMPT_RE.search(prompt or "")
    if m:
        return float(m.group(1)), f"parsed '{m.group(0)}' from the design prompt"
    return DEFAULT_SAFETY_FACTOR, "default_assumption (no safety factor in run_record or prompt)"


def derive_bcs(mesh: MeshData, parameters: dict, prompt: str) -> BCSpec:
    """Apply the documented heuristic. Raises BCUnresolvable with the exact
    unmet condition."""
    load_n, load_source = resolve_load_n(parameters, prompt)

    zmin, zmax = mesh.bbox[2], mesh.bbox[5]
    height = max(zmax - zmin, 1e-9)
    cylinders = [s for s in mesh.surfaces if s.kind == "Cylinder"]
    if not cylinders:
        raise BCUnresolvable("no cylindrical (hole) faces to fix — the heuristic "
                             "anchors the part at its mounting holes")
    lowest_z = min(s.centroid[2] for s in cylinders)
    fixed_surfs = [s for s in cylinders
                   if s.centroid[2] <= lowest_z + HOLE_GROUP_TOL * height]
    fixed_nodes = sorted({t for s in fixed_surfs for t in s.node_tags})

    footprint = ((mesh.bbox[3] - mesh.bbox[0]) * (mesh.bbox[4] - mesh.bbox[1])) or 1e-9
    planes = [s for s in mesh.surfaces
              if s.kind == "Plane" and s.area_mm2 >= LOAD_FACE_MIN_AREA * footprint
              and not set(s.node_tags) <= set(fixed_nodes)]
    if not planes:
        raise BCUnresolvable("no planar face large enough to be the load plate "
                             f"(>= {LOAD_FACE_MIN_AREA:.0%} of the bbox footprint)")
    load_face = max(planes, key=lambda s: s.centroid[2])

    cloads, excluded_fraction = consistent_face_loads(
        mesh, load_face, -load_n, dof=3, exclude=set(fixed_nodes))

    description = {
        "heuristic": "lowest-Z hole group fixed (all DOFs); highest-Z large "
                     "planar face loaded -Z with consistent TRI6 nodal loads",
        "fixed": {"surfaces": [s.tag for s in fixed_surfs],
                  "surface_centroids_z_mm": [round(s.centroid[2], 3) for s in fixed_surfs],
                  "nodes": len(fixed_nodes), "dofs": "1-3"},
        "load": {"surface": load_face.tag, "face_area_mm2": round(load_face.area_mm2, 2),
                 "face_centroid_z_mm": round(load_face.centroid[2], 3),
                 "total_force_n": load_n, "direction": "-Z (assumption)",
                 "source": load_source, "loaded_nodes": len(cloads),
                 "share_excluded_on_fixed_nodes": round(excluded_fraction, 4)},
        "audit_note": "boundary conditions are heuristic approximations — "
                      "review before trusting the verdict",
    }
    return BCSpec(fixed=[FixedSet("FIXED", fixed_nodes)], cloads=cloads,
                  description=description)


def run_fea(step_path: Path, out_dir: Path, material: dict, parameters: dict,
            prompt: str, mesh_size_mm: float | None = None,
            timeout_s: float = 300.0) -> tuple[CheckResult, dict]:
    """Full Layer 2 pipeline. Returns (check, fea_block). Never raises:
    every failure mode becomes an honest not_run/fail with real evidence."""
    fea: dict = {"material": material}
    if material.get("e_mpa") is None or material.get("yield_mpa") is None:
        return CheckResult("fea_static", NOT_RUN,
                           reason=f"material '{material.get('name')}' has no "
                                  "elastic properties in the table"), fea
    if not find_ccx():
        return CheckResult("fea_static", NOT_RUN,
                           reason=f"ccx not found on PATH (and CCX_BIN unset) — "
                                  f"{INSTALL_HINT}"), fea

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        mesh = mesh_step(step_path, out_dir / "mesh.inp", mesh_size_mm)
    except MeshError as exc:
        return CheckResult("fea_static", NOT_RUN, reason=f"meshing failed: {exc}"), fea
    fea["mesh"] = {"nodes": mesh.node_count, "elements": mesh.element_count,
                   "element_type": mesh.element_type,
                   "mesh_size_mm": mesh.mesh_size_mm}

    try:
        bcs = derive_bcs(mesh, parameters, prompt)
    except BCUnresolvable as exc:
        return CheckResult("fea_static", NOT_RUN, value=fea.get("mesh"),
                           reason=f"boundary conditions unresolvable: {exc}"), fea
    fea["boundary_conditions"] = bcs.description

    write_deck(out_dir / "job.inp", "mesh.inp", mesh.elsets, material, bcs)
    try:
        run_ccx(out_dir, "job", timeout_s=timeout_s)
        results = parse_frd(out_dir / "job.frd")
    except SolverError as exc:
        fea["solver"] = {"log_path": str(out_dir / "ccx.log")}
        return CheckResult("fea_static", NOT_RUN, value=fea.get("mesh"),
                           reason=f"solver failed: {exc}"), fea

    sf, sf_source = resolve_safety_factor(parameters, prompt)
    allowable = material["yield_mpa"] / sf
    fea["results"] = {**results, "yield_mpa": material["yield_mpa"],
                      "safety_factor": sf, "safety_factor_source": sf_source,
                      "allowable_mpa": round(allowable, 3)}
    fea["solver"] = {"log_path": str(out_dir / "ccx.log"),
                     "frd_path": str(out_dir / "job.frd"),
                     "deck_path": str(out_dir / "job.inp")}

    value = {"max_von_mises_mpa": results["max_von_mises_mpa"],
             "allowable_mpa": round(allowable, 3),
             "max_displacement_mm": results["max_displacement_mm"],
             "material": material["name"], "material_source": material["source"],
             "safety_factor": sf}
    if results["max_von_mises_mpa"] <= allowable:
        return CheckResult(
            "fea_static", PASS, value=value,
            reason=None), fea
    return CheckResult(
        "fea_static", FAIL, value=value,
        reason=f"max von Mises {results['max_von_mises_mpa']:.1f} MPa exceeds "
               f"allowable {allowable:.1f} MPa (= {material['yield_mpa']} MPa "
               f"yield / SF {sf}; material {material['name']}, "
               f"{material['source']}); BCs are heuristic — see "
               "boundary_conditions in the fea block"), fea
