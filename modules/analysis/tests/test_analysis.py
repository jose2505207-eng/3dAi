"""Offline tests for run_analysis and the CLI (fake LLM client, no network)."""

import json

import pytest

from modules.analysis.__main__ import main as cli_main
from modules.analysis.analyze import (AnalysisError, AnalysisInputError,
                                      run_analysis)
from modules.analysis.tests.conftest import (CLEAN_REPLY, FABRICATED_REPLY,
                                             SIM_REPORT_FAIL, FakeClient)
from shared.llm import LLMError


def test_writes_summary_and_record(make_run_dir):
    run_dir = make_run_dir()
    record = run_analysis(run_dir, FakeClient([CLEAN_REPLY]))

    assert record.success
    assert (run_dir / "analysis.md").read_text().strip() == CLEAN_REPLY.strip()
    assert record.summary_path == str(run_dir / "analysis.md")
    # inputs provenance: both consumed files, hashed
    assert [i["path"].split("/")[-1] for i in record.inputs] \
        == ["run_record.json", "sim_report.json"]
    assert all(len(i["sha256"]) == 64 and i["bytes"] > 0 for i in record.inputs)
    # a real (fake-)call record, preflight ok
    assert record.call_record["called"] is True
    assert record.call_record["http_status"] == 200
    assert record.preflight["ok"] is True
    # fully grounded summary -> nothing flagged
    assert record.grounding["flagged"] == []
    assert record.grounding["allowed_numbers_count"] > 0
    # on-disk record matches
    on_disk = json.loads((run_dir / "analysis_record.json").read_text())
    assert on_disk == record.to_dict()
    assert on_disk["success"] is True


def test_summary_of_failing_run(make_run_dir):
    run_dir = make_run_dir(sim_report=SIM_REPORT_FAIL)
    reply = ("**Verdict: fail.** mass 470.4 g exceeds the 200 g budget; "
             "fea_static did not run: ccx nonpositive jacobian in element 5163.")
    record = run_analysis(run_dir, FakeClient([reply]))
    assert record.success  # the SUMMARY succeeded; it reports a failing part
    assert record.grounding["flagged"] == []


def test_grounding_flags_fabricated_number(make_run_dir):
    run_dir = make_run_dir()
    record = run_analysis(run_dir, FakeClient([FABRICATED_REPLY]))
    assert record.success  # default is warn, not fail
    assert "9.7" in record.grounding["flagged"]
    on_disk = json.loads((run_dir / "analysis_record.json").read_text())
    assert "9.7" in on_disk["grounding"]["flagged"]


def test_missing_sim_report_refuses(make_run_dir):
    run_dir = make_run_dir(omit=("sim_report.json",))
    with pytest.raises(AnalysisInputError, match="sim_report.json"):
        run_analysis(run_dir, FakeClient([CLEAN_REPLY]))
    assert not (run_dir / "analysis.md").exists()
    assert cli_main([str(run_dir)]) == 2  # input check precedes client config


def test_missing_run_record_refuses(make_run_dir):
    run_dir = make_run_dir(omit=("run_record.json",))
    with pytest.raises(AnalysisInputError, match="run_record.json"):
        run_analysis(run_dir, FakeClient([CLEAN_REPLY]))
    assert cli_main([str(run_dir)]) == 2


def test_wrong_schema_refuses(make_run_dir):
    bogus = dict(SIM_REPORT_FAIL, schema="sim_report/v999")
    run_dir = make_run_dir(sim_report=bogus)
    with pytest.raises(AnalysisInputError, match="sim_report/v999"):
        run_analysis(run_dir, FakeClient([CLEAN_REPLY]))


def test_cli_exit_codes_strict_vs_default(make_run_dir):
    run_dir = make_run_dir()
    assert cli_main([str(run_dir)], client=FakeClient([FABRICATED_REPLY])) == 0
    assert cli_main([str(run_dir), "--strict"],
                    client=FakeClient([FABRICATED_REPLY])) == 1
    assert cli_main([str(run_dir), "--strict"],
                    client=FakeClient([CLEAN_REPLY])) == 0


def test_llm_failure_surfaces_with_record(make_run_dir):
    run_dir = make_run_dir()
    err = LLMError("html_response", "endpoint returned HTML, likely a proxy/filter")
    with pytest.raises(AnalysisError, match="LLM call failed") as exc:
        run_analysis(run_dir, FakeClient([err]))
    record = exc.value.record
    assert record.success is False
    assert "proxy/filter" in record.failure
    # the failure record is still on disk for audit; no summary was written
    on_disk = json.loads((run_dir / "analysis_record.json").read_text())
    assert on_disk["success"] is False
    assert not (run_dir / "analysis.md").exists()
    assert cli_main([str(run_dir)],
                    client=FakeClient([LLMError("network", "boom")])) == 2


def test_preflight_failure_refuses_to_run(make_run_dir):
    class DeadClient(FakeClient):
        def preflight(self):
            raise LLMError("network", "request to http://fake:8000/v1/models failed")

    run_dir = make_run_dir()
    client = DeadClient([CLEAN_REPLY])
    with pytest.raises(AnalysisError, match="preflight failed"):
        run_analysis(run_dir, client)
    assert client.prompts_seen == []  # never called the model
    on_disk = json.loads((run_dir / "analysis_record.json").read_text())
    assert on_disk["preflight"]["ok"] is False


def test_empty_reply_is_a_failure(make_run_dir):
    run_dir = make_run_dir()
    with pytest.raises(AnalysisError, match="empty summary"):
        run_analysis(run_dir, FakeClient(["   \n"]))
