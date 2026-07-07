"""Layer 2 (FEA) tests — offline, no droplet, no LLM.

Tests that need the CalculiX binary skip with an install hint when it is
absent; meshing/BC-heuristic/parser tests need only the gmsh SDK (a venv
dependency). The analytic anchor is a uniaxial tension bar: sigma = F/A,
delta = FL/AE — solver plumbing is asserted against the hand calculation.
"""

import math

import pytest

from modules.simulation.ccx import (BCSpec, FixedSet, find_ccx, parse_frd,
                                    run_ccx, write_deck)
from modules.simulation.fea import (BCUnresolvable, consistent_face_loads,
                                    derive_bcs, resolve_load_n,
                                    resolve_safety_factor)
from modules.simulation.mesher import mesh_step

needs_ccx = pytest.mark.skipif(
    find_ccx() is None,
    reason="ccx not installed — sudo apt-get install -y calculix-ccx")

AL = {"name": "aluminum_6061", "density_g_cm3": 2.70, "e_mpa": 68_900,
      "nu": 0.33, "yield_mpa": 276, "source": "env"}


def _export_step(shape, path):
    import cadquery as cq
    cq.exporters.export(shape, str(path))


def _bar_step(tmp_path):
    import cadquery as cq
    path = tmp_path / "bar.step"
    _export_step(cq.Workplane("XY").box(100, 10, 10), path)  # centered at origin
    return path


def _plate_step(tmp_path):
    import cadquery as cq
    plate = (cq.Workplane("XY").box(60, 40, 5).faces(">Z").workplane()
             .pushPoints([(22, 12), (-22, 12), (22, -12), (-22, -12)]).hole(6.0))
    path = tmp_path / "plate.step"
    _export_step(plate, path)
    return path


@needs_ccx
def test_tension_bar_matches_hand_calc(tmp_path):
    """100x10x10 bar, F=1000 N axial: sigma = F/A = 10 MPa exactly,
    delta = FL/AE = 0.01451 mm. 3-2-1 restraint keeps the field uniform."""
    mesh = mesh_step(_bar_step(tmp_path), tmp_path / "mesh.inp", mesh_size_mm=4.0)

    def face_at(x):
        planes = [s for s in mesh.surfaces if s.kind == "Plane"]
        return min(planes, key=lambda s: abs(s.centroid[0] - x))

    def node_at(x, y, z):
        return min(mesh.nodes, key=lambda t: math.dist(mesh.nodes[t], (x, y, z)))

    fixed_face = face_at(-50.0)
    load_face = face_at(50.0)
    cloads, excluded = consistent_face_loads(mesh, load_face, 1000.0, dof=1)
    assert excluded == 0.0
    assert sum(v for _, _, v in cloads) == pytest.approx(1000.0)

    bcs = BCSpec(
        fixed=[FixedSet("XFACE", sorted(fixed_face.node_tags), 1, 1),
               FixedSet("PINA", [node_at(-50, -5, -5)], 2, 3),
               FixedSet("PINB", [node_at(-50, 5, -5)], 3, 3)],
        cloads=cloads)
    write_deck(tmp_path / "job.inp", "mesh.inp", mesh.elsets, AL, bcs)
    run_ccx(tmp_path, "job")
    results = parse_frd(tmp_path / "job.frd")

    assert results["max_von_mises_mpa"] == pytest.approx(10.0, rel=0.07)
    delta = 1000.0 * 100.0 / (100.0 * 68_900.0)  # 0.014514 mm
    assert results["max_displacement_mm"] == pytest.approx(delta, rel=0.10)


def test_bc_heuristic_on_plate(tmp_path):
    mesh = mesh_step(_plate_step(tmp_path), tmp_path / "mesh.inp", mesh_size_mm=4.0)
    bcs = derive_bcs(mesh, {"load_n": 500.0}, "a mounting plate")

    desc = bcs.description
    assert len(desc["fixed"]["surfaces"]) == 4          # all four hole faces
    assert desc["load"]["total_force_n"] == 500.0
    assert "load_n" in desc["load"]["source"]
    assert desc["load"]["face_centroid_z_mm"] == pytest.approx(2.5, abs=0.1)  # top
    assert desc["load"]["direction"].startswith("-Z")
    assert "heuristic" in desc["audit_note"]
    # applied load is exact despite excluded fixed-node shares
    assert sum(v for _, _, v in bcs.cloads) == pytest.approx(-500.0)
    assert all(dof == 3 for _, dof, _ in bcs.cloads)


def test_no_holes_means_bcs_unresolvable(tmp_path):
    import cadquery as cq
    path = tmp_path / "box.step"
    _export_step(cq.Workplane("XY").box(20, 20, 20), path)
    mesh = mesh_step(path, tmp_path / "mesh.inp", mesh_size_mm=6.0)
    with pytest.raises(BCUnresolvable, match="no cylindrical"):
        derive_bcs(mesh, {"load_n": 100.0}, "")


def test_no_load_magnitude_means_bcs_unresolvable():
    with pytest.raises(BCUnresolvable, match="no load magnitude"):
        resolve_load_n({"plate_l": 60.0}, "a bracket with no numbers")


def test_load_and_sf_resolution_sources():
    load, src = resolve_load_n({}, "a bracket that holds 500 N under 200 g")
    assert load == 500.0 and "prompt" in src
    load, src = resolve_load_n({"load_n": 750.0}, "")
    assert load == 750.0 and "load_n" in src
    sf, src = resolve_safety_factor({}, "with a safety factor of 2.5")
    assert sf == 2.5 and "prompt" in src
    sf, src = resolve_safety_factor({}, "")
    assert sf == 2.0 and "default_assumption" in src


def test_parse_frd_fixed_width():
    frd = "\n".join([
        "    1C  model",
        "  100CL  101 1.000000000         938                     0    1           1",
        " -4  DISP        4    1",
        " -5  D1          1    2    1    0",
        " -1         7 1.00000E-02 2.00000E-02 2.00000E-03",
        " -3",
        " -4  STRESS      6    1",
        " -5  SXX         1    4    1    1",
        " -1         7 1.00000E+01 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00",
        " -1         9 2.00000E+00 2.00000E+00 2.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00",
        " -3",
        "9999",
    ])
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.frd"
        f.write_text(frd)
        results = parse_frd(f)
    # uniaxial 10 MPa -> vM 10; hydrostatic 2 MPa -> vM 0 (node 9 not the max)
    assert results["max_von_mises_mpa"] == pytest.approx(10.0)
    assert results["max_stress_node"] == 7
    assert results["max_displacement_mm"] == pytest.approx(
        math.sqrt(0.01 ** 2 + 0.02 ** 2 + 0.002 ** 2), abs=1e-5)


@needs_ccx
def test_full_pipeline_writes_fea_block(make_run_dir, monkeypatch):
    import cadquery as cq
    monkeypatch.setenv("MATERIAL", "aluminum_6061")
    plate = (cq.Workplane("XY").box(60, 40, 5).faces(">Z").workplane()
             .pushPoints([(22, 12), (-22, 12), (22, -12), (-22, -12)]).hole(6.0))
    run_dir = make_run_dir(plate, {"load_n": 500.0, "safety_factor": 2.0},
                           prompt="a plate that holds 500 N")

    from modules.simulation import run_checks
    report = run_checks(run_dir, fea_mesh_size_mm=4.0)
    fea_check = {c.name: c for c in report.checks}["fea_static"]

    assert fea_check.status in ("pass", "fail")  # solved, honest either way
    assert report.fea["mesh"]["elements"] > 0
    assert report.fea["boundary_conditions"]["load"]["total_force_n"] == 500.0
    assert report.fea["results"]["allowable_mpa"] == pytest.approx(138.0)
    assert (run_dir / "fea" / "job.frd").exists()
    assert (run_dir / "fea" / "ccx.log").exists()


def test_fea_not_run_without_ccx(make_run_dir, monkeypatch):
    """With ccx unreachable the check is not_run with the install hint —
    the solver is never stubbed."""
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.delenv("CCX_BIN", raising=False)
    import cadquery as cq
    run_dir = make_run_dir(cq.Workplane("XY").box(10, 10, 10), {"load_n": 100.0})
    from modules.simulation import run_checks
    report = run_checks(run_dir)
    fea_check = {c.name: c for c in report.checks}["fea_static"]
    assert fea_check.status == "not_run"
    assert "ccx not found" in fea_check.reason and "apt-get" in fea_check.reason
