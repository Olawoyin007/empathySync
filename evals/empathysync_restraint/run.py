"""Run the restraint eval: preflight, then a memory-safe, resumable eval_set.

Usage:
    python -m evals.empathysync_restraint.run                 # starter dataset
    python -m evals.empathysync_restraint.run --limit 20
    python -m evals.empathysync_restraint.run --judge qwen2.5:14b-instruct-q4_K_M
    python -m evals.empathysync_restraint.run --no-preflight  # skip the guard

Pause with Ctrl-C. Re-run the SAME command to resume - eval_set reuses the log
dir and finishes only the samples that did not complete. Robustness (retry,
resume, logging, limits) comes from Inspect; the preflight guard and the
memory-safe defaults (one model call at a time) are ours.

This never activates anything on a schedule. It runs once, when you run it.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import (
    DEFAULT_ENGINE,
    DEFAULT_JUDGE,
    DEFAULT_LOG_DIR,
    DEFAULT_OLLAMA_HOST,
    STARTER_DATASET,
)
from .preflight import preflight


def main() -> int:
    parser = argparse.ArgumentParser(prog="empathysync-restraint-eval")
    parser.add_argument("--dataset", default=str(STARTER_DATASET))
    parser.add_argument("--engine", default=DEFAULT_ENGINE, help="model under test")
    parser.add_argument("--judge", default=DEFAULT_JUDGE, help="restraint grader")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST)
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--limit", type=int, default=None, help="cap number of samples")
    parser.add_argument("--headroom", type=float, default=8.0, help="GB of RAM headroom")
    parser.add_argument("--max-connections", type=int, default=1)
    parser.add_argument("--no-preflight", action="store_true")
    args = parser.parse_args()

    if not args.no_preflight:
        fatals, warnings = preflight(
            args.host, [args.engine, args.judge], headroom_gb=args.headroom
        )
        for w in warnings:
            print(f"WARNING: {w}")
        if fatals:
            for fatal in fatals:
                print(f"FATAL: {fatal}")
            print("Refusing to start. Fix the above (or pass --no-preflight).")
            return 1

    # Import Inspect lazily so --help and preflight failures stay fast.
    from inspect_ai import eval_set

    from .task import empathysync_restraint

    print(
        f"engine={args.engine}  judge={args.judge}  host={args.host}\n"
        f"dataset={args.dataset}\nlog_dir={args.log_dir}  "
        f"(Ctrl-C is safe; re-run the same command to resume)"
    )

    success, logs = eval_set(
        tasks=[
            empathysync_restraint(
                dataset_path=args.dataset,
                engine=args.engine,
                judge=args.judge,
                ollama_host=args.host,
            )
        ],
        log_dir=args.log_dir,
        max_connections=args.max_connections,
        max_samples=1,
        limit=args.limit,
        retry_attempts=3,
    )

    print(
        f"\nDone. success={success}. Browse results with:\n  inspect view --log-dir {args.log_dir}"
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
