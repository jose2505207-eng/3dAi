# agentic-mechanical-engineer — Modules 1+2 (design + simulation) with the
# full FEA toolchain (gmsh mesher + CalculiX solver).
#
# No endpoint or secret is baked in. Runtime env: VLLM_BASE_URL, MODEL_NAME,
# MATERIAL, CAD_MAX_ITERATIONS.
#
#   docker build -t ame:dev .
#   docker run --rm -e VLLM_BASE_URL=http://<droplet>:8000/v1 \
#     -v $(pwd)/outputs:/app/outputs ame:dev \
#     python -m modules.design "<prompt>"
#   docker run --rm -v $(pwd)/outputs:/app/outputs ame:dev \
#     python -m modules.simulation outputs/design/<run-dir>
#
# Web UI on the droplet (co-located with Gemma, so VLLM_BASE_URL is
# localhost; --network host makes localhost:8000 reachable and exposes :8080.
# NO auth yet — do not expose this publicly until the auth gate is added):
#   docker run --rm --network host \
#     -e VLLM_BASE_URL=http://localhost:8000/v1 -e MODEL_NAME=google/gemma-3-27b-it \
#     -e CAD_MAX_ITERATIONS=8 \
#     -v $(pwd)/outputs:/app/outputs ame:dev \
#     uvicorn orchestrator.server:app --host 0.0.0.0 --port 8080

# -bookworm pinned deliberately: Debian trixie (current python:*-slim default)
# dropped the calculix-ccx binary package ("no installation candidate",
# verified 2026-07-07); bookworm ships calculix-ccx 2.20-1.
FROM python:3.11-slim-bookworm

# calculix-ccx: the FEA solver (`ccx` binary).
# The rest are runtime .so deps of the gmsh/cadquery wheels, each named by an
# actual failure: libGLU.so.1 by `import gmsh` on a bare host, and the
# libxcursor1..libgomp1 block by `ldd /usr/local/lib/libgmsh.so` ("not found")
# in this image on 2026-07-07.
RUN apt-get update && apt-get install -y --no-install-recommends \
        calculix-ccx \
        libglu1-mesa \
        libgl1 \
        libxrender1 \
        libxext6 \
        libsm6 \
        libxcursor1 \
        libxft2 \
        libxinerama1 \
        libfontconfig1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Into the image's SYSTEM python, no venv: the design sandbox spawns
# `python -I` subprocesses, so cadquery must be importable by the image
# interpreter itself. This heavy layer (cadquery/OCP + gmsh) sits before the
# source copy so code edits don't re-download it.
RUN pip install --no-cache-dir cadquery gmsh pytest fastapi uvicorn

COPY . .

# Overridable usage banner (CMD, not ENTRYPOINT).
CMD ["python", "-c", "print('agentic-mechanical-engineer\\n\\nUsage:\\n  python -m modules.design \"<prompt>\"            # needs -e VLLM_BASE_URL=http://<host>:8000/v1\\n  python -m modules.simulation <run-dir>         # e.g. outputs/design/<stamp>-<slug>\\n\\nMount outputs to keep results: -v $(pwd)/outputs:/app/outputs')"]
