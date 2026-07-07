# modules/simulation — Module 2

Layer 1: deterministic checks (CadQuery/OCP, no solver).
Layer 2: static FEA — gmsh meshing + CalculiX (ccx) solve.

```sh
python -m modules.simulation <module-1-run-dir>   # writes sim_report.json
#   --no-fea         skip Layer 2 (fea_static reports not_run)
#   --mesh-size MM   FEA mesh size (default: bbox diagonal / 20)
#   --fea-timeout S  ccx timeout (default 300)
```

Exit codes: 0 no check failed, 1 a check failed, 2 config/IO error.

## Toolchain install (exact commands)

gmsh comes from PyPI into the project venv (already in the dev setup):

```sh
.venv/bin/pip install gmsh          # gmsh SDK, meshes STEP -> C3D10 tets
```

CalculiX is a system package (no PyPI build). Debian/Ubuntu — laptop **and**
droplet:

```sh
sudo apt-get install -y calculix-ccx     # provides the `ccx` solver binary
```

Non-standard install? Point the module at the binary with `CCX_BIN=/path/to/ccx`.
If ccx is missing the `fea_static` check reports **not_run** with this install
hint — the solver is never stubbed and a missing toolchain is never a pass.

## FEA model (Layer 2)

- Mesh: gmsh, 2nd-order tets (C3D10); gmsh itself writes the Abaqus-format
  mesh (it owns the gmsh→Abaqus node-ordering conversion).
- Material: same config as Layer 1 (`MATERIAL` env; default assumption
  aluminum_6061 — E 68.9 GPa, ν 0.33, yield 276 MPa, 2.70 g/cm³). The name,
  values, and source (env vs default_assumption) are recorded in the report.
- Boundary conditions are a **documented heuristic**, recorded verbatim in
  `sim_report.json → fea.boundary_conditions` for human audit: the lowest-Z
  group of cylindrical (hole) faces is fixed (all DOFs); the load is applied
  straight down (-Z) on the highest-Z large planar face as consistent TRI6
  nodal loads. Load magnitude comes from a load/force-named run_record
  parameter, else `"<number> N"` parsed from the design prompt — its source
  is recorded. Unresolvable BCs ⇒ `fea_static` is **not_run**, never pass.
- Verdict: `max_von_mises <= yield / safety_factor` (safety factor from
  run_record parameter or prompt, else a recorded default assumption of 2.0).
- Raw artifacts stay in `<run-dir>/fea/`: `mesh.inp`, `job.inp` (deck),
  `job.frd`, `job.dat`, `ccx.log`.

## Tests

```sh
.venv/bin/pytest modules/simulation/tests/
```

Offline (no droplet, no LLM). The analytic anchor is a 100×10×10 mm tension
bar: σ = F/A = 10 MPa, δ = FL/AE — parsed solver results must match the hand
calculation. ccx-dependent tests skip with an install hint when the solver is
absent.
