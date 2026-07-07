"""Unit tests for the numeric grounding heuristic."""

from modules.analysis.grounding import (allowed_numbers, extract_number_tokens,
                                        flag_ungrounded)
from modules.analysis.tests.conftest import RUN_RECORD, SIM_REPORT_PASS


def test_allow_set_walks_nested_inputs():
    allowed = allowed_numbers(RUN_RECORD, SIM_REPORT_PASS)
    for expected in (500.0, 2.0, 200.0,        # prompt text
                     60.0, 6.0,                # parameters
                     12000.0, 32.4, 41.3,      # check values
                     2970.0, 0.021,            # fea mesh + results
                     2.7, 276.0):              # material
        assert any(abs(expected - a) <= 0.01 for a in allowed), expected


def test_tolerance_absorbs_rounding():
    allowed = {470.4, 0.021}
    assert flag_ungrounded("mass is 470 g, deflection 0.0209 mm", allowed) == []


def test_fabricated_number_is_flagged():
    assert flag_ungrounded("safety factor of 9.7", {500.0, 2.0}) == ["9.7"]


def test_list_markers_and_identifiers_ignored():
    text = "1. first point\n2) second point\nelements are C3D10 type, mm^3 units"
    assert extract_number_tokens(text, skip_list_markers=True) == []


def test_comma_grouped_numbers_parse():
    assert flag_ungrounded("the mesh has 2,970 nodes", {2970.0}) == []


def test_flagged_deduplicated_in_order():
    flagged = flag_ungrounded("9.7 then 88 then 9.7 again", {1.0})
    assert flagged == ["9.7", "88"]
