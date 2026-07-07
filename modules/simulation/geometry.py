"""STEP inspection for the deterministic checks (CadQuery/OCP, no solver).

`inspect_step` never raises: a STEP that cannot be loaded comes back as
GeometryFacts(loaded=False, error=<the real exception text>) so the checks
can fail/skip honestly with the evidence attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeometryFacts:
    loaded: bool
    error: str | None = None
    solid_count: int = 0
    volume_mm3: float = 0.0
    bbox_mm: list[float] = field(default_factory=list)
    all_solids_valid: bool = False
    watertight: bool = False
    cylindrical_face_radii_mm: list[float] = field(default_factory=list)


def inspect_step(step_path: Path) -> GeometryFacts:
    import cadquery as cq
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    try:
        shape = cq.importers.importStep(str(step_path)).val()
    except Exception as exc:  # surface the real importer error, never mask it
        return GeometryFacts(loaded=False,
                             error=f"STEP import failed: {type(exc).__name__}: {exc}")

    solids = shape.Solids()
    shells = [sh for solid in solids for sh in solid.Shells()]
    bb = shape.BoundingBox()
    radii = []
    for face in shape.Faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            radii.append(round(float(adaptor.Cylinder().Radius()), 4))

    return GeometryFacts(
        loaded=True,
        solid_count=len(solids),
        volume_mm3=float(sum(s.Volume() for s in solids)),
        bbox_mm=[round(float(v), 4) for v in (bb.xlen, bb.ylen, bb.zlen)],
        all_solids_valid=bool(solids) and all(s.isValid() for s in solids),
        watertight=bool(shells) and all(sh.wrapped.Closed() for sh in shells),
        cylindrical_face_radii_mm=sorted(radii),
    )
