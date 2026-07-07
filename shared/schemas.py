"""Typed schemas shared across modules (stdlib dataclasses, JSON on disk).

Modules communicate through files + these schemas, never through imports of
each other's internals (wiki/pages/architecture.md).

Honesty doctrine (same as shared/llm.py): a check is `pass`, `fail`, or
`not_run`. A check that could not run is `not_run` WITH the reason — never
`pass`, never silently omitted. `fail` and `not_run` require a reason.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASS, FAIL, NOT_RUN = "pass", "fail", "not_run"
CHECK_STATUSES = (PASS, FAIL, NOT_RUN)

# Overall verdicts: `incomplete` = nothing failed but at least one check
# could not run — deliberately distinct from a clean `pass`.
VERDICT_PASS, VERDICT_FAIL, VERDICT_INCOMPLETE = "pass", "fail", "incomplete"

SIM_REPORT_SCHEMA = "sim_report/v1"
SIM_REPORT_FILENAME = "sim_report.json"


@dataclass
class CheckResult:
    """One deterministic check. `value` is the measured evidence (JSON-
    serializable); `reason` is mandatory unless the check passed."""

    name: str
    status: str
    value: Any = None
    reason: str | None = None

    def __post_init__(self):
        if self.status not in CHECK_STATUSES:
            raise ValueError(f"check '{self.name}': illegal status {self.status!r} "
                             f"(must be one of {CHECK_STATUSES})")
        if self.status != PASS and not self.reason:
            raise ValueError(f"check '{self.name}': status {self.status!r} requires "
                             "a reason — a check may never fail or skip silently")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimReport:
    """Module 2's output and Module 3's input. Written as sim_report.json
    into the Module 1 run dir it was computed from."""

    verdict: str
    checks: list[CheckResult]
    material: dict | None      # {name, density_g_cm3, source} or None if unresolved
    provenance: dict           # inputs consumed (path, sha256, bytes), timestamp, ...
    schema: str = SIM_REPORT_SCHEMA

    @staticmethod
    def verdict_of(checks: list[CheckResult]) -> str:
        statuses = {c.status for c in checks}
        if FAIL in statuses:
            return VERDICT_FAIL
        return VERDICT_PASS if statuses == {PASS} else VERDICT_INCOMPLETE

    def to_dict(self) -> dict:
        return {"schema": self.schema, "verdict": self.verdict,
                "material": self.material,
                "checks": [c.to_dict() for c in self.checks],
                "provenance": self.provenance}

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def file_provenance(path: Path) -> dict | None:
    """sha256 + size of a consumed input, or None if it does not exist."""
    import hashlib
    if not path.exists():
        return None
    return {"path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}
