"""STEP → quadratic tetra mesh via the gmsh SDK.

gmsh itself writes the Abaqus-format mesh file (nodes + C3D10 elements) —
it owns the gmsh→Abaqus midside-node reordering, which is easy to get
silently wrong by hand. We additionally extract per-surface facts (type,
nodes, TRI6 connectivity, area, centroid) for the BC heuristic; gmsh node
tags are preserved verbatim in the .inp, so node sets built from them are
valid in the CalculiX deck.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path


class MeshError(Exception):
    """Meshing failed; message carries the real gmsh error."""


@dataclass
class SurfaceInfo:
    tag: int
    kind: str                 # gmsh geometric type: "Plane", "Cylinder", ...
    node_tags: set[int]
    tri6: list[tuple[int, ...]]   # 6-node triangles (3 corners + 3 midsides)
    area_mm2: float
    centroid: tuple[float, float, float]


@dataclass
class MeshData:
    inp_path: Path            # mesh-only .inp written by gmsh
    elsets: list[str]         # element set names found in the .inp
    node_count: int
    element_count: int
    element_type: str
    mesh_size_mm: float
    bbox: tuple[float, float, float, float, float, float]  # xmin..zmax
    surfaces: list[SurfaceInfo] = field(default_factory=list)
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)


def _tri_area(p0, p1, p2) -> float:
    ux, uy, uz = (p1[i] - p0[i] for i in range(3))
    vx, vy, vz = (p2[i] - p0[i] for i in range(3))
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def mesh_step(step_path: Path, inp_path: Path, mesh_size_mm: float | None = None) -> MeshData:
    """Mesh a STEP solid to 2nd-order tets and write a mesh-only .inp.
    Raises MeshError with the real gmsh failure text."""
    try:
        import gmsh
    except ImportError as exc:
        raise MeshError(f"gmsh SDK not installed ({exc}) — pip install gmsh") from exc

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(step_path))
        volumes = gmsh.model.getEntities(3)
        if not volumes:
            raise MeshError(f"{step_path} contains no volume to mesh")
        # A physical volume group makes gmsh write ONLY volume elements to
        # the .inp — stray 2D shells would be section-less elements CalculiX
        # refuses to solve.
        gmsh.model.addPhysicalGroup(3, [t for _, t in volumes], name="PART")

        bbox = gmsh.model.getBoundingBox(-1, -1)
        diag = math.dist(bbox[:3], bbox[3:])
        size = mesh_size_mm or max(diag / 20.0, 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = {int(t): (coords[3 * i], coords[3 * i + 1], coords[3 * i + 2])
                 for i, t in enumerate(node_tags)}
        etypes, etags, _ = gmsh.model.mesh.getElements(3)
        element_count = sum(len(t) for t in etags)
        if element_count == 0:
            raise MeshError("gmsh produced no volume elements")

        surfaces = []
        for _, tag in gmsh.model.getEntities(2):
            stags, _, _ = gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)
            tri6: list[tuple[int, ...]] = []
            for et, _, enodes in zip(*gmsh.model.mesh.getElements(2, tag)):
                n_per = gmsh.model.mesh.getElementProperties(et)[3]
                flat = [int(n) for n in enodes]
                tri6 += [tuple(flat[i:i + n_per]) for i in range(0, len(flat), n_per)]
            area = sum(_tri_area(nodes[t[0]], nodes[t[1]], nodes[t[2]]) for t in tri6)
            stag_set = {int(t) for t in stags}
            if not stag_set:
                continue
            cx = [sum(nodes[t][i] for t in stag_set) / len(stag_set) for i in range(3)]
            surfaces.append(SurfaceInfo(
                tag=tag, kind=gmsh.model.getType(2, tag), node_tags=stag_set,
                tri6=tri6, area_mm2=area, centroid=(cx[0], cx[1], cx[2])))

        gmsh.write(str(inp_path))
    except MeshError:
        raise
    except Exception as exc:  # surface the real gmsh error, never mask it
        raise MeshError(f"gmsh failed on {step_path}: {type(exc).__name__}: {exc}") from exc
    finally:
        gmsh.finalize()

    elsets = sorted(set(re.findall(r"ELSET=(\w+)", inp_path.read_text())))
    if not elsets:
        raise MeshError(f"{inp_path} contains no element set — cannot assign a section")
    return MeshData(inp_path=inp_path, elsets=elsets, node_count=len(nodes),
                    element_count=element_count, element_type="C3D10",
                    mesh_size_mm=round(size, 3), bbox=tuple(bbox),
                    surfaces=surfaces, nodes=nodes)
