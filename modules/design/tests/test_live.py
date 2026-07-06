"""Live smoke test against the real Gemma/vLLM endpoint.

Skips gracefully when VLLM_BASE_URL is unset. Run it from a network path
that can actually reach the droplet (on the droplet or tethered — a laptop
content filter intercepting plain HTTP will fail preflight, by design).

    VLLM_BASE_URL=http://<droplet>:8000/v1 .venv/bin/pytest modules/design/tests/test_live.py -v
"""

import json
import os

import pytest

from modules.design.loop import run_design
from shared.llm import LLMClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("VLLM_BASE_URL"),
    reason="VLLM_BASE_URL not set — live Gemma endpoint test skipped")

PROMPT = ("a rectangular mounting plate 60 mm x 40 mm x 5 mm "
          "with a 6 mm hole in each corner, holes 8 mm from the edges")


def test_full_loop_produces_valid_manifold_step(tmp_path):
    client = LLMClient.from_env()
    record = run_design(PROMPT, tmp_path, client=client)

    assert record.success, record.failure
    final = record.iterations[-1]
    assert final.geometry["is_valid_solid"] and final.geometry["is_closed"]
    assert final.geometry["volume_mm3"] > 0

    # the STEP file re-imports as a valid closed solid
    import cadquery as cq
    solid = cq.importers.importStep(str(tmp_path / "part.step")).val()
    assert solid.isValid()
    assert float(solid.Volume()) > 0

    # provenance: a real Gemma call, not a stub — endpoint, model, response id
    on_disk = json.loads((tmp_path / "run_record.json").read_text())
    for it in on_disk["iterations"]:
        llm = it["llm"]
        assert llm["called"] is True
        assert llm["http_status"] == 200
        assert llm["endpoint"].startswith(os.environ["VLLM_BASE_URL"].rstrip("/"))
        assert llm["model"] == client.model
        assert llm["response_id"]  # vLLM stamps an id on every real completion
    assert on_disk["preflight"]["ok"] is True
