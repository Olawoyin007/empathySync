"""Run the restraint eval: preflight, then a memory-safe, resumable eval_set.

Usage:
    python -m evals.empathysync_restraint.run                 # restraint side (judge)
    python -m evals.empathysync_restraint.run --mode domain   # classifier side (no judge)
    python -m evals.empathysync_restraint.run --limit 20
    python -m evals.empathysync_restraint.run --judge qwen2.5:14b-instruct-q4_K_M
    python -m evals.empathysync_restraint.run --no-preflight  # skip the guard

Two modes of the one eval:
  restraint (default) - a judge grades whether the *response* held restraint.
                        Loads the big judge; needs real RAM headroom.
  domain              - rule-based check that the *classifier* routed the prompt
                        into a restraint-triggering domain. No judge, so it runs
                        on modest hardware.

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


def _write_verdict(logs, path: str, mode: str, dataset: str) -> None:
    """Best-effort structured verdict from Inspect's returned logs, in the SAME
    result.json shape intentKeeper writes, so the nightly DAG surfaces both evals
    identically. Runs after the eval and only reads its logs, so it cannot change
    the eval result. Callers wrap it in try/except - a failure here is a warning,
    never a failed eval.

    INCORRECT samples become failed_checks; NOANSWER (a fail-closed judge/pipeline
    error) is counted separately, never treated as a pass or a violation.
    """
    import hashlib
    import json
    from pathlib import Path

    from inspect_ai.log import read_eval_log
    from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER

    log = logs[0]
    if log.samples is None and getattr(log, "location", None):
        log = read_eval_log(log.location)  # returned logs can be header-only
    res = log.results
    samples = log.samples or []
    total = (res.completed_samples if res else None) or len(samples)

    # Headline number = Inspect's own accuracy metric (what `inspect view` shows).
    score_pct = 0.0
    if res and res.scores:
        metrics = res.scores[0].metrics
        m = metrics.get("accuracy") or next(iter(metrics.values()), None)
        if m is not None:
            score_pct = round(m.value * 100, 1)

    correct = errors = 0
    failed = []
    for s in samples:
        sc = next(iter((s.scores or {}).values()), None)
        val = sc.value if sc else None
        if val == CORRECT:
            correct += 1
        elif val == NOANSWER:
            errors += 1
        elif val == INCORRECT:
            md = (sc.metadata if sc else {}) or {}
            failed.append(
                {
                    "expected": "pass" if mode == "restraint" else "restraint domain",
                    "got": str(sc.answer) if sc and sc.answer is not None else str(val),
                    "confidence": float(md.get("confidence") or 0.0),
                    "content": (
                        str(s.input)[:120]
                        + (f" | {sc.explanation[:140]}" if sc and sc.explanation else "")
                    ),
                }
            )

    result = {
        "eval": f"empathysync-{mode}",
        "eval_version": os.environ.get("EVAL_VERSION", "dev"),
        "dataset": dataset,
        "dataset_hash": hashlib.sha256(Path(dataset).read_bytes()).hexdigest()[:12],
        "score_pct": score_pct,
        "correct": correct,
        "total": total,
        "errors": errors,
        "failed_checks": failed,
    }
    Path(path).write_text(json.dumps(result, indent=2))
    print(f"wrote verdict: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="empathysync-restraint-eval")
    parser.add_argument(
        "--mode",
        choices=["restraint", "domain"],
        default="restraint",
        help="restraint = judge grades the response; domain = rule-based classifier check (no judge)",
    )
    parser.add_argument("--dataset", default=str(STARTER_DATASET))
    parser.add_argument(
        "--engine", default=os.getenv("OLLAMA_MODEL") or DEFAULT_ENGINE, help="model under test"
    )
    parser.add_argument(
        "--judge", default=DEFAULT_JUDGE, help="restraint grader (restraint mode only)"
    )
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST)
    parser.add_argument(
        "--log-dir",
        default=None,
        help="default: logs/restraint (restraint mode) or logs/domain (domain mode)",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap number of samples")
    parser.add_argument("--headroom", type=float, default=8.0, help="GB of RAM headroom")
    parser.add_argument("--max-connections", type=int, default=1)
    parser.add_argument("--no-preflight", action="store_true")
    parser.add_argument(
        "--result-json",
        default=None,
        help="also write a structured verdict (same shape as intentKeeper) here",
    )
    args = parser.parse_args()

    # Each mode is a different task; keep their logs apart so eval_set resume
    # never crosses them. Restraint mode keeps its existing logs/restraint path.
    if args.log_dir is None:
        args.log_dir = str(
            DEFAULT_LOG_DIR if args.mode == "restraint" else DEFAULT_LOG_DIR.parent / "domain"
        )

    # Domain mode never loads the judge, so it does not need judge headroom.
    needed_models = [args.engine] if args.mode == "domain" else [args.engine, args.judge]

    if not args.no_preflight:
        fatals, warnings = preflight(args.host, needed_models, headroom_gb=args.headroom)
        for w in warnings:
            print(f"WARNING: {w}")
        if fatals:
            for fatal in fatals:
                print(f"FATAL: {fatal}")
            print("Refusing to start. Fix the above (or pass --no-preflight).")
            return 1

    # Import Inspect lazily so --help and preflight failures stay fast.
    from inspect_ai import eval_set

    from .task import empathysync_domain, empathysync_restraint

    if args.mode == "domain":
        the_task = empathysync_domain(
            dataset_path=args.dataset, engine=args.engine, ollama_host=args.host
        )
        grader = "rule-based (no judge)"
    else:
        the_task = empathysync_restraint(
            dataset_path=args.dataset,
            engine=args.engine,
            judge=args.judge,
            ollama_host=args.host,
        )
        grader = args.judge

    print(
        f"mode={args.mode}  engine={args.engine}  grader={grader}  host={args.host}\n"
        f"dataset={args.dataset}\nlog_dir={args.log_dir}  "
        f"(Ctrl-C is safe; re-run the same command to resume)"
    )

    success, logs = eval_set(
        tasks=[the_task],
        log_dir=args.log_dir,
        max_connections=args.max_connections,
        max_samples=1,
        limit=args.limit,
        retry_attempts=3,
    )

    print(
        f"\nDone. success={success}. Browse results with:\n  inspect view --log-dir {args.log_dir}"
    )

    if args.result_json:
        try:
            _write_verdict(logs, args.result_json, args.mode, args.dataset)
        except Exception as e:  # a verdict-file problem must never fail the eval
            print(f"WARNING: could not write verdict json: {e}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
