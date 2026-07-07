"""Offline tests for AST safety validation and sandboxed execution.

Needs cadquery installed (it is a module dependency, not a network one).
"""

import pytest

from modules.design.sandbox import CADScriptError, run_script, validate_script

GOOD_BOX = """
import cadquery as cq

length = 40.0
width = 20.0
height = 10.0
hole_d = 5.0

result = (cq.Workplane("XY").box(length, width, height)
          .faces(">Z").workplane().hole(hole_d))
"""


def test_validate_script_accepts_good_code():
    assert validate_script(GOOD_BOX) == []


@pytest.mark.parametrize("code,fragment", [
    ("import os\nresult = os.getcwd()", "import of 'os' not allowed"),
    ("from subprocess import run\nresult = None", "import from 'subprocess'"),
    ("result = open('/etc/passwd').read()", "use of 'open' not allowed"),
    ("result = (1).__class__", "dunder attribute access"),
    ("result = ", "syntax error"),
])
def test_validate_script_rejects(code, fragment):
    violations = validate_script(code)
    assert violations and fragment in "; ".join(violations)


def test_run_script_builds_valid_watertight_solid(tmp_path):
    report = run_script(GOOD_BOX, tmp_path / "part.step", tmp_path / "part.stl")
    assert report.volume_mm3 > 0
    assert report.is_valid_solid and report.is_closed
    assert report.solid_count == 1
    assert report.cylindrical_faces >= 1  # hole_d was actually cut
    assert (tmp_path / "part.step").stat().st_size > 0
    assert (tmp_path / "part.stl").stat().st_size > 84


def test_run_script_rejects_disconnected_solids(tmp_path):
    # Two boxes 50 mm apart: union() succeeds but yields 2 floating bodies.
    code = """
import cadquery as cq
result = (cq.Workplane("XY").box(10, 10, 5)
          .union(cq.Workplane("XY").transformed(offset=(50, 0, 0)).box(10, 10, 5)))
"""
    with pytest.raises(CADScriptError, match="2 DISCONNECTED solids") as exc:
        run_script(code, tmp_path / "p.step", tmp_path / "p.stl")
    assert exc.value.phase == "validation"


def test_run_script_rejects_declared_but_uncut_holes(tmp_path):
    # hole_diameter is a parameter, but nothing is ever cut — the Gemma
    # failure mode Module 2 caught on the bracket run.
    code = """
import cadquery as cq
hole_diameter = 6.0
result = cq.Workplane("XY").box(60, 40, 5)
"""
    with pytest.raises(CADScriptError, match="ZERO cylindrical faces") as exc:
        run_script(code, tmp_path / "p.step", tmp_path / "p.stl")
    assert exc.value.phase == "validation"
    assert "hole_diameter" in str(exc.value)  # names the offending parameter


def test_run_script_surfaces_real_traceback(tmp_path):
    code = "import cadquery as cq\nresult = cq.Workplane('XY').box(0, 0, 0)"
    with pytest.raises(CADScriptError) as exc:
        run_script(code, tmp_path / "p.step", tmp_path / "p.stl")
    assert exc.value.phase in ("execution", "validation")
    assert str(exc.value)  # non-empty, model-feedable message


def test_run_script_requires_result_variable(tmp_path):
    code = "import cadquery as cq\nsolid = cq.Workplane('XY').box(1, 1, 1)"
    with pytest.raises(CADScriptError, match="variable named 'result'"):
        run_script(code, tmp_path / "p.step", tmp_path / "p.stl")


def test_run_script_rejects_unsafe_before_subprocess(tmp_path):
    with pytest.raises(CADScriptError, match="safety validator") as exc:
        run_script("import socket\nresult = None",
                   tmp_path / "p.step", tmp_path / "p.stl")
    assert exc.value.phase == "safety"
