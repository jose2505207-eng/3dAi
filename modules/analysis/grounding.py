"""Numeric grounding check: surface numbers in the summary that don't come
from the inputs.

This is a HEURISTIC that SURFACES suspect numeric tokens — not a proof of
correctness. It will have false positives (a correctly-derived ratio or unit
conversion is not literally in the inputs) and false negatives (a fabricated
number can coincide with an unrelated input number). It therefore WARNS by
default; only the CLI's --strict turns a flag into a failing exit code. It
does not guarantee the absence of fabrication.
"""

from __future__ import annotations

import re

# Unsigned numeric tokens: 42, 470.4, 2,970, 6.89e4. The lookarounds keep us
# out of identifiers ("C3D10", "v0.2.1") and unit exponents ("mm^3") while
# still matching a number at the end of a sentence ("of 9.7."); magnitudes
# only — sign errors are not the fabrication class this hunts.
NUM_RE = re.compile(r"(?<![\w.^])\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?(?!\w|\.\d)")
# Markdown ordered-list markers ("1. ", "2) ") are structure, not claims.
LIST_MARKER_RE = re.compile(r"^\s{0,3}\d+[.)]\s", re.MULTILINE)

REL_TOL = 0.01   # ~1 % — absorbs the model rounding a reported float
ABS_TOL = 0.01   # floor for values near zero


def _to_float(token: str) -> float:
    return float(token.replace(",", ""))


def extract_number_tokens(text: str, skip_list_markers: bool = False) -> list[str]:
    if skip_list_markers:
        text = LIST_MARKER_RE.sub("", text)
    return NUM_RE.findall(text)


def _walk(obj, out: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        out.update(_to_float(t) for t in extract_number_tokens(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, out)


def allowed_numbers(run_record: dict, sim_report: dict) -> set[float]:
    """Allow-set of numeric magnitudes the summary may legitimately quote:
    run_record prompt/parameters/outputs, and the ENTIRE sim_report (every
    check value and reason, fea block, material properties, provenance)."""
    out: set[float] = set()
    _walk(run_record.get("prompt"), out)
    _walk(run_record.get("parameters"), out)
    _walk(run_record.get("outputs"), out)
    _walk(sim_report, out)
    return out


def _matches(v: float, allowed: set[float]) -> bool:
    return any(abs(v - a) <= max(ABS_TOL, REL_TOL * max(v, a)) for a in allowed)


def flag_ungrounded(text: str, allowed: set[float]) -> list[str]:
    """Numeric tokens in `text` (list markers excluded) with no ~1 %-tolerant
    match in the allow-set. Deduplicated, in order of first appearance."""
    flagged: list[str] = []
    seen: set[float] = set()
    for token in extract_number_tokens(text, skip_list_markers=True):
        v = _to_float(token)
        if _matches(v, allowed) or v in seen:
            continue
        seen.add(v)
        flagged.append(token)
    return flagged
