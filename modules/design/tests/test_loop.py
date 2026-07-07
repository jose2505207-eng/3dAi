"""Offline tests for the self-correction loop, with a fake LLM client.

The fake mimics shared.llm.LLMClient's surface (.model, .base_url,
.preflight(), .chat()) so the loop's behavior is tested end to end —
including real sandboxed CadQuery execution — without any network.
"""

import json

import pytest

from modules.design.loop import DesignError, extract_parameters, run_design
from shared.llm import CallRecord, LLMError

BROKEN = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10)  # missing arg"
GOOD = """import cadquery as cq
plate_l = 60.0
plate_w = 40.0
plate_t = 5.0
result = cq.Workplane("XY").box(plate_l, plate_w, plate_t)
"""


class FakeClient:
    base_url = "http://fake:8000/v1"
    model = "google/gemma-3-27b-it"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts_seen = []

    def preflight(self):
        return {"data": [{"id": self.model}]}

    def chat(self, system, user, temperature=0.4):
        self.prompts_seen.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        record = CallRecord(called=True, endpoint=f"{self.base_url}/chat/completions",
                            model=self.model, http_status=200,
                            response_id=f"fake-{len(self.prompts_seen)}", latency_s=0.01)
        return reply, record


def test_loop_feeds_real_error_back_and_converges(tmp_path):
    client = FakeClient([f"```python\n{BROKEN}\n```", f"```python\n{GOOD}\n```"])
    record = run_design("a simple plate", tmp_path, client=client)

    assert record.success
    assert [it.passed for it in record.iterations] == [False, True]
    assert record.iterations[0].phase == "execution"
    # the retry prompt must contain the previous script AND the real error
    assert BROKEN.splitlines()[1] in client.prompts_seen[1]
    assert record.iterations[0].error.splitlines()[0].startswith("CAD script failed")
    assert "CAD script failed" in client.prompts_seen[1]
    # provenance: every iteration records a real call
    for it in record.iterations:
        assert it.llm["called"] is True
        assert it.llm["http_status"] == 200
        assert it.llm["endpoint"].endswith("/chat/completions")
    # outputs on disk
    assert (tmp_path / "part.step").exists()
    assert (tmp_path / "part.stl").exists()
    assert (tmp_path / "part.py").read_text().strip() == GOOD.strip()
    on_disk = json.loads((tmp_path / "run_record.json").read_text())
    assert on_disk["success"] is True
    assert on_disk["parameters"] == {"plate_l": 60.0, "plate_w": 40.0, "plate_t": 5.0}


def test_loop_budget_exhaustion_raises_with_record(tmp_path):
    client = FakeClient([BROKEN, BROKEN])
    with pytest.raises(DesignError, match="budget"):
        run_design("a plate", tmp_path, client=client, max_iterations=2)
    on_disk = json.loads((tmp_path / "run_record.json").read_text())
    assert on_disk["success"] is False
    assert len(on_disk["iterations"]) == 2
    assert "budget" in on_disk["failure"]


def test_llm_failure_is_surfaced_not_retried(tmp_path):
    html_err = LLMError("html_response", "endpoint returned HTML, likely a proxy/filter"
                        " — check network path. HTTP 302; body starts: '<html>'")
    client = FakeClient([html_err, GOOD])
    with pytest.raises(DesignError, match="LLM call failed") as exc:
        run_design("a plate", tmp_path, client=client, max_iterations=3)
    record = exc.value.record
    assert len(record.iterations) == 1  # no retry after an LLM failure
    assert record.iterations[0].phase == "llm"
    assert "proxy/filter" in record.failure


def test_preflight_failure_refuses_to_run(tmp_path):
    class DeadClient(FakeClient):
        def preflight(self):
            raise LLMError("network", "request to http://fake:8000/v1/models failed")

    client = DeadClient([GOOD])
    with pytest.raises(DesignError, match="preflight failed"):
        run_design("a plate", tmp_path, client=client)
    assert client.prompts_seen == []  # never called the model
    on_disk = json.loads((tmp_path / "run_record.json").read_text())
    assert on_disk["preflight"]["ok"] is False


def test_on_iteration_surfaces_live_progress(tmp_path):
    client = FakeClient([BROKEN, GOOD])
    events = []
    run_design("a plate", tmp_path, client=client,
               on_iteration=lambda n, b, phase, err: events.append((n, b, phase, err)))
    # attempt start, failed outcome with the REAL error, attempt start, ok
    assert [(n, b, p) for n, b, p, _ in events] \
        == [(1, 5, "llm"), (1, 5, "execution"), (2, 5, "llm"), (2, 5, "ok")]
    assert "CAD script failed" in events[1][3]
    assert events[0][3] is None and events[3][3] is None


def test_extract_parameters():
    assert extract_parameters("x = 5\ny = -2.5\nname = 'a'\nz = x + 1\nflag = True") \
        == {"x": 5, "y": -2.5}
