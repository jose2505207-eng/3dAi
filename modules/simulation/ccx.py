"""CalculiX driver: write the input deck, run ccx, parse the .frd.

The solver is never stubbed. If ccx is missing or crashes, the caller gets
the real evidence (install hint / return code / log tail) via SolverError,
and the FEA check reports not_run — never pass.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

INSTALL_HINT = "install CalculiX: sudo apt-get install -y calculix-ccx (Debian/Ubuntu)"


class SolverError(Exception):
    """ccx could not produce results; message carries the real evidence."""


@dataclass
class FixedSet:
    name: str                  # NSET name in the deck (A-Z0-9_)
    node_tags: list[int]
    first_dof: int = 1
    last_dof: int = 3


@dataclass
class BCSpec:
    fixed: list[FixedSet]
    cloads: list[tuple[int, int, float]]     # (node, dof, force)
    description: dict = field(default_factory=dict)  # human-auditable record


def find_ccx() -> str | None:
    return os.environ.get("CCX_BIN") or shutil.which("ccx")


def _nset_lines(tags: list[int]) -> str:
    lines = []
    for i in range(0, len(tags), 8):
        lines.append(", ".join(str(t) for t in tags[i:i + 8]) + ",")
    return "\n".join(lines)


def write_deck(deck_path: Path, mesh_inp_name: str, elsets: list[str],
               material: dict, bcs: BCSpec) -> None:
    parts = [f"*INCLUDE, INPUT={mesh_inp_name}"]
    for fs in bcs.fixed:
        parts += [f"*NSET, NSET={fs.name}", _nset_lines(fs.node_tags)]
    parts.append("*BOUNDARY")
    for fs in bcs.fixed:
        parts.append(f"{fs.name}, {fs.first_dof}, {fs.last_dof}")
    parts += [f"*MATERIAL, NAME={material['name'].upper()}",
              "*ELASTIC",
              f"{material['e_mpa']:.1f}, {material['nu']:.3f}"]
    for elset in elsets:
        parts.append(f"*SOLID SECTION, ELSET={elset}, MATERIAL={material['name'].upper()}")
    parts += ["*STEP", "*STATIC", "*CLOAD"]
    parts += [f"{node}, {dof}, {value:.6g}" for node, dof, value in bcs.cloads]
    parts += ["*NODE FILE", "U", "*EL FILE", "S", "*END STEP", ""]
    deck_path.write_text("\n".join(parts))


def run_ccx(workdir: Path, jobname: str, timeout_s: float = 300.0) -> str:
    """Run ccx on <jobname>.inp in workdir; returns the solver log text.
    Raises SolverError with real evidence on any failure."""
    ccx = find_ccx()
    if not ccx:
        raise SolverError(f"ccx not found on PATH (and CCX_BIN unset) — {INSTALL_HINT}")
    env = {**os.environ, "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "2")}
    try:
        proc = subprocess.run([ccx, "-i", jobname], cwd=workdir, env=env,
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise SolverError(f"ccx exceeded the {timeout_s:.0f}s timeout") from exc

    log = (proc.stdout or "") + (proc.stderr or "")
    (workdir / "ccx.log").write_text(log)
    frd = workdir / f"{jobname}.frd"
    if proc.returncode != 0 or not frd.exists():
        tail = "\n".join(log.strip().splitlines()[-15:]) or "no solver output"
        raise SolverError(f"ccx failed (exit {proc.returncode}, "
                          f"{'no ' if not frd.exists() else ''}.frd produced); "
                          f"log tail:\n{tail}")
    return log


def parse_frd(frd_path: Path) -> dict:
    """Extract max von Mises (MPa) and max displacement magnitude (mm) from
    a CalculiX .frd. Fixed-width blocks: ' -4  DISP'/' -4  STRESS' headers,
    ' -1' data rows of node(10ch) + 12-char floats."""
    max_disp, max_vm = None, None
    vm_node = disp_node = None
    block = None
    for line in frd_path.read_text().splitlines():
        if line.startswith(" -4"):
            name = line[5:11].strip()
            block = name if name in ("DISP", "STRESS") else None
            continue
        if block is None or not line.startswith(" -1"):
            continue
        node = int(line[3:13])
        vals = [float(line[13 + 12 * i:25 + 12 * i])
                for i in range((len(line) - 13) // 12)]
        if block == "DISP" and len(vals) >= 3:
            d = math.sqrt(vals[0] ** 2 + vals[1] ** 2 + vals[2] ** 2)
            if max_disp is None or d > max_disp:
                max_disp, disp_node = d, node
        elif block == "STRESS" and len(vals) >= 6:
            sxx, syy, szz, sxy, syz, szx = vals[:6]
            vm = math.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2
                                  + (szz - sxx) ** 2)
                           + 3.0 * (sxy ** 2 + syz ** 2 + szx ** 2))
            if max_vm is None or vm > max_vm:
                max_vm, vm_node = vm, node
    if max_vm is None or max_disp is None:
        raise SolverError(f"{frd_path} contains no "
                          f"{'STRESS' if max_vm is None else 'DISP'} block — "
                          "solver output incomplete")
    return {"max_von_mises_mpa": round(max_vm, 3), "max_stress_node": vm_node,
            "max_displacement_mm": round(max_disp, 6), "max_disp_node": disp_node}
