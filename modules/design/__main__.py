"""CLI: python -m modules.design "<prompt>" [--out DIR] [--max-iterations N]

Prints the run record JSON to stdout and writes part.step / part.stl /
part.py / run_record.json to the output directory.

Exit codes: 0 = valid solid produced; 1 = loop failed (budget exhausted);
2 = configuration/endpoint failure (VLLM_BASE_URL unset, preflight failed,
LLM call failed) — the run record still carries the real evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path

from modules.design.loop import DesignError, run_design
from shared.llm import LLMClient, LLMError


def default_out_dir(prompt: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:40] or "part"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs/design") / f"{stamp}-{slug}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m modules.design",
        description="Natural-language prompt -> Gemma -> CadQuery -> STEP/STL")
    parser.add_argument("prompt", help="natural-language part description")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default outputs/design/<stamp>-<slug>)")
    parser.add_argument("--max-iterations", type=int, default=None,
                        help="self-correction budget (default CAD_MAX_ITERATIONS or 5)")
    parser.add_argument("--cad-timeout", type=float, default=120.0,
                        help="per-script sandbox timeout in seconds (default 120)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out_dir = args.out or default_out_dir(args.prompt)

    try:
        client = LLMClient.from_env()
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        record = run_design(args.prompt, out_dir, client=client,
                            max_iterations=args.max_iterations,
                            cad_timeout_s=args.cad_timeout)
    except DesignError as exc:
        print(json.dumps(exc.record.to_dict(), indent=2))
        print(f"\nerror: {exc}", file=sys.stderr)
        preflight_ok = bool(exc.record.preflight and exc.record.preflight.get("ok"))
        llm_failed = any(it.phase == "llm" for it in exc.record.iterations)
        return 2 if (not preflight_ok or llm_failed) else 1

    print(json.dumps(record.to_dict(), indent=2))
    print(f"\nOK: wrote {record.outputs['step']} and {record.outputs['stl']} "
          f"in {len(record.iterations)} iteration(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
