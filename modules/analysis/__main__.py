"""CLI: python -m modules.analysis <run-dir> [--strict] [--temperature T]

<run-dir> must contain run_record.json (Module 1) AND sim_report.json
(Module 2). Writes analysis.md + analysis_record.json into it and prints
analysis_record.json to stdout.

Exit codes: 0 = summary written; 1 = --strict and the grounding check flagged
at least one number; 2 = config/endpoint/LLM failure OR missing/invalid
inputs (the failure record is still printed when one exists).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.analysis.analyze import (AnalysisError, AnalysisInputError,
                                      load_inputs, run_analysis)
from shared.llm import LLMClient, LLMError


def main(argv: list[str] | None = None, client: LLMClient | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m modules.analysis",
        description="Module 1+2 run dir -> Gemma -> grounded analysis.md")
    parser.add_argument("run_dir", type=Path,
                        help="run dir containing run_record.json and sim_report.json")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if the grounding check flags any number")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="sampling temperature (default 0.3)")
    args = parser.parse_args(argv)

    # Validate inputs before touching the endpoint: a half-run dir is a
    # refusal regardless of LLM availability.
    try:
        load_inputs(args.run_dir)
    except AnalysisInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if client is None:
        try:
            client = LLMClient.from_env()
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        record = run_analysis(args.run_dir, client,
                              temperature=args.temperature, strict=args.strict)
    except AnalysisError as exc:
        print(json.dumps(exc.record.to_dict(), indent=2))
        print(f"\nerror: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(record.to_dict(), indent=2))
    flagged = record.grounding["flagged"]
    if args.strict and flagged:
        print(f"\nstrict: grounding flagged {len(flagged)} number(s) — failing",
              file=sys.stderr)
        return 1
    print(f"\nOK: wrote {record.summary_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
