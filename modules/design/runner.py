"""Subprocess entry point: execute one CadQuery script, validate, export.

Invoked as: python -I runner.py <script.py> <out.step> <out.stl>
The script has ALREADY passed AST safety validation (sandbox.validate_script).

Standalone by design — no project imports, so it runs under `python -I`.

Prints exactly one JSON line of geometry metrics to stdout on success
(exit 0), including the validation verdicts the parent judges:
  volume_mm3 > 0, is_valid_solid (BRepCheck), is_closed (every shell
  watertight), solid_count >= 1.
Exit 2 = the script's fault (feed stderr back to the model).
"""

import json
import sys


def fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 2


def main() -> int:
    script_path, step_path, stl_path = sys.argv[1], sys.argv[2], sys.argv[3]

    import cadquery as cq

    namespace: dict = {"cq": cq, "cadquery": cq}
    with open(script_path) as f:
        code = f.read()
    exec(compile(code, "cad_script.py", "exec"), namespace)  # noqa: S102

    result = namespace.get("result")
    if result is None:
        return fail("script must assign the final solid to a variable named 'result'")

    shape = result.val() if hasattr(result, "val") else result
    if not hasattr(shape, "Volume"):
        return fail(f"'result' is not a CadQuery shape (got {type(result).__name__})")

    solids = shape.Solids() if hasattr(shape, "Solids") else []
    volume = float(shape.Volume())
    bb = shape.BoundingBox()
    is_valid = bool(shape.isValid())
    # Watertight/manifold: every shell of every solid must be closed.
    shells = [sh for solid in solids for sh in solid.Shells()]
    is_closed = bool(shells) and all(sh.wrapped.Closed() for sh in shells)
    # Cylindrical faces: evidence that declared holes were actually cut
    # (concave/convex not distinguished — bosses count too, same caveat as
    # Module 2's hole_geometry check).
    faces = shape.Faces() if hasattr(shape, "Faces") else []
    cylindrical_faces = sum(1 for f in faces if f.geomType() == "CYLINDER")

    cq.exporters.export(result, step_path)
    cq.exporters.export(result, stl_path, tolerance=0.1)

    print(json.dumps({
        "volume_mm3": volume,
        "bbox_mm": [float(bb.xlen), float(bb.ylen), float(bb.zlen)],
        "solid_count": len(solids),
        "is_valid_solid": is_valid,
        "is_closed": is_closed,
        "cylindrical_faces": cylindrical_faces,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
