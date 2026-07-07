"""Live smoke test against the real Gemma/vLLM endpoint.

Skips gracefully when VLLM_BASE_URL is unset — mirrors
modules/design/tests/test_live.py.

    VLLM_BASE_URL=http://<droplet>:8000/v1 .venv/bin/pytest modules/analysis/tests/test_live.py -v
"""

import os

import pytest

from modules.analysis.analyze import run_analysis
from shared.llm import LLMClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("VLLM_BASE_URL"),
    reason="VLLM_BASE_URL not set — live Gemma endpoint test skipped")


def test_live_summary_is_written_and_provenanced(make_run_dir):
    run_dir = make_run_dir()  # passing fixture run dir; the LLM call is real
    client = LLMClient.from_env()
    record = run_analysis(run_dir, client)

    assert record.success, record.failure
    summary = (run_dir / "analysis.md").read_text()
    assert len(summary.strip()) > 100  # a real summary, not a token
    # provenance: a real Gemma call, not a stub
    assert record.preflight["ok"] is True
    assert record.call_record["called"] is True
    assert record.call_record["http_status"] == 200
    assert record.call_record["response_id"]  # vLLM stamps every completion
    assert record.call_record["endpoint"].startswith(
        os.environ["VLLM_BASE_URL"].rstrip("/"))
    # grounding ran (flags allowed — it's a heuristic; must be recorded)
    assert isinstance(record.grounding["flagged"], list)
    assert record.grounding["allowed_numbers_count"] > 0
