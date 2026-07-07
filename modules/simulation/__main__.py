"""CLI: python -m modules.simulation <run-dir>

<run-dir> is a Module 1 output dir (part.step, part.stl, run_record.json).
Writes sim_report.json into it (Module 3's input) and prints the report.

Exit codes: 0 = no check failed (verdict pass or incomplete — not_run checks
are visible in the report, never hidden); 1 = at least one check failed;
2 = configuration/IO error (not a Module 1 run dir, unreadable inputs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.simulation.checks import RunDirError, run_checks
from shared.schemas import SIM_REPORT_FILENAME, VERDICT_FAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m modules.simulation",
        description="Layer 1 deterministic checks on a Module 1 run dir")
    parser.add_argument("run_dir", type=Path,
                        help="Module 1 output dir (part.step + run_record.json)")
    args = parser.parse_args(argv)

    try:
        report = run_checks(args.run_dir)
    except RunDirError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report.write(args.run_dir / SIM_REPORT_FILENAME)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"\nverdict: {report.verdict} — wrote "
          f"{args.run_dir / SIM_REPORT_FILENAME}", file=sys.stderr)
    return 1 if report.verdict == VERDICT_FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
