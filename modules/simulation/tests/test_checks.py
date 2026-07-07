"""Offline tests for the Layer 1 deterministic checks (no network, no LLM)."""

import json

import pytest

from modules.simulation import RunDirError, run_checks
from modules.simulation.__main__ import main as cli_main
from shared.schemas import FAIL, NOT_RUN, PASS, CheckResult


def _box(l=60.0, w=40.0, h=5.0):
    import cadquery as cq
    return cq.Workplane("XY").box(l, w, h)


def _by_name(report):
    return {c.name: c for c in report.checks}


def test_box_bbox_and_mass_math(make_run_dir, monkeypatch):
    # 60x40x5 mm = 12 cm^3; steel_1018 (explicit config) -> 94.44 g
    monkeypatch.setenv("MATERIAL", "steel_1018")
    run_dir = make_run_dir(_box(), {"plate_l": 60.0, "plate_w": 40.0,
                                    "plate_t": 5.0, "max_mass_g": 200.0})
    checks = _by_name(run_checks(run_dir))

    assert checks["geometry_valid"].status == PASS
    assert checks["single_body"].status == PASS

    bbox = checks["bounding_box"]
    assert bbox.status == PASS
    assert sorted(bbox.value["bbox_mm"]) == [5.0, 40.0, 60.0]

    mass = checks["mass_budget"]
    assert mass.status == PASS
    assert mass.value["volume_cm3"] == pytest.approx(12.0)
    assert mass.value["mass_g"] == pytest.approx(94.44, abs=0.01)
    assert mass.value["density_source"] == "env"
    assert mass.value["material"] == "steel_1018"


def test_mass_over_budget_fails(make_run_dir, monkeypatch):
    monkeypatch.setenv("MATERIAL", "steel_1018")
    run_dir = make_run_dir(_box(), {"plate_l": 60.0, "plate_w": 40.0,
                                    "plate_t": 5.0, "max_mass_g": 50.0})
    mass = _by_name(run_checks(run_dir))["mass_budget"]
    assert mass.status == FAIL
    assert "94.4" in mass.reason and "50" in mass.reason


def test_two_solids_fail_single_body(make_run_dir):
    import cadquery as cq
    s1 = cq.Workplane("XY").box(20, 20, 5)
    s2 = cq.Workplane("XY").transformed(offset=(50, 0, 0)).box(10, 10, 5)
    compound = cq.Compound.makeCompound([s1.val(), s2.val()])
    run_dir = make_run_dir(compound, {})

    report = run_checks(run_dir)
    single = _by_name(report)["single_body"]
    assert single.status == FAIL
    assert single.value["solids"] == 2
    assert "2 solids" in single.reason
    assert report.verdict == "fail"


def test_missing_material_makes_mass_constraint_not_run(make_run_dir):
    # MATERIAL unset (autouse fixture): mass is computed with the recorded
    # default assumption but the constraint is not_run — NEVER pass.
    run_dir = make_run_dir(_box(), {"plate_l": 60.0, "plate_w": 40.0,
                                    "plate_t": 5.0, "max_mass_g": 200.0})
    mass = _by_name(run_checks(run_dir))["mass_budget"]
    assert mass.status == NOT_RUN
    assert "assumption" in mass.reason
    assert mass.value["mass_g"] == pytest.approx(32.4, abs=0.01)  # 12 cm^3 * 2.70
    assert mass.value["density_source"] == "default_assumption"


def test_unknown_material_is_not_run_with_reason(make_run_dir, monkeypatch):
    monkeypatch.setenv("MATERIAL", "unobtainium")
    run_dir = make_run_dir(_box(), {"max_mass_g": 200.0})
    mass = _by_name(run_checks(run_dir))["mass_budget"]
    assert mass.status == NOT_RUN
    assert "unobtainium" in mass.reason
    assert "mass_g" not in (mass.value or {})  # no density -> no mass claimed


def test_hole_geometry_pass_and_fail(make_run_dir):
    import cadquery as cq
    plate = (cq.Workplane("XY").box(60, 40, 5).faces(">Z").workplane()
             .pushPoints([(22, 12), (-22, 12), (22, -12), (-22, -12)]).hole(6.0))

    run_dir = make_run_dir(plate, {"hole_d": 6.0})
    holes = _by_name(run_checks(run_dir))["hole_geometry"]
    assert holes.status == PASS
    assert 6.0 in holes.value["observed_diameters_mm"]

    (run_dir / "run_record.json").write_text(json.dumps({"parameters": {"hole_d": 8.0}}))
    holes = _by_name(run_checks(run_dir))["hole_geometry"]
    assert holes.status == FAIL
    assert "8.0" in holes.reason


def test_min_wall_thickness_is_honest_not_run(make_run_dir):
    run_dir = make_run_dir(_box(), {})
    wall = _by_name(run_checks(run_dir))["min_wall_thickness"]
    assert wall.status == NOT_RUN
    assert "not implemented in Layer 1" in wall.reason


def test_no_dimension_params_bbox_not_run(make_run_dir):
    run_dir = make_run_dir(_box(), {"hole_d": 6.0})
    bbox = _by_name(run_checks(run_dir))["bounding_box"]
    assert bbox.status == NOT_RUN
    assert bbox.value["bbox_mm"]  # still reports the measurement


def test_report_written_and_verdict_incomplete_without_fail(make_run_dir):
    run_dir = make_run_dir(_box(), {"plate_l": 60.0, "plate_w": 40.0, "plate_t": 5.0})
    rc = cli_main([str(run_dir)])
    assert rc == 0  # nothing failed (min_wall_thickness not_run is not a fail)
    on_disk = json.loads((run_dir / "sim_report.json").read_text())
    assert on_disk["schema"] == "sim_report/v1"
    assert on_disk["verdict"] == "incomplete"
    statuses = {c["name"]: c["status"] for c in on_disk["checks"]}
    assert statuses["min_wall_thickness"] == "not_run"
    prov = on_disk["provenance"]
    assert prov["inputs"]["part.step"]["sha256"]
    assert prov["design"]["prompt"] == "test part"


def test_cli_exit_codes(make_run_dir, tmp_path):
    import cadquery as cq
    s1 = cq.Workplane("XY").box(20, 20, 5)
    s2 = cq.Workplane("XY").transformed(offset=(50, 0, 0)).box(10, 10, 5)
    run_dir = make_run_dir(cq.Compound.makeCompound([s1.val(), s2.val()]), {})
    assert cli_main([str(run_dir)]) == 1  # single_body failed

    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli_main([str(empty)]) == 2  # not a Module 1 run dir


def test_run_dir_contract_errors(tmp_path):
    with pytest.raises(RunDirError, match="not a directory"):
        run_checks(tmp_path / "nope")


def test_check_result_refuses_silent_failure():
    with pytest.raises(ValueError, match="requires a reason"):
        CheckResult("x", FAIL)
    with pytest.raises(ValueError, match="illegal status"):
        CheckResult("x", "skipped", reason="r")
