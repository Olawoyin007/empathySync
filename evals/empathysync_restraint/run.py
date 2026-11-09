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
from pathlib import Path

from .config import (
    DEFAULT_ENGINE,
    DEFAULT_JUDGE,
    DEFAULT_LOG_DIR,
    DEFAULT_OLLAMA_HOST,
    STARTER_DATASET,
)
from .preflight import preflight, resolve_max_loaded, resolve_slots


def _pipeline_models(engine: str) -> list[str]:
    """Every model the empathySync pipeline loads for this engine.

    See also `_pipeline_num_ctx` for the context those requests carry.

    The pipeline loads more than the engine: the classifier and the optional
    safety guard come from the app's .env. Passing only the engine is how the
    guard in #247 went uncounted. Read them through the app's own settings, with
    the same fallback the classifier uses (the eval pins OLLAMA_MODEL to the
    engine), so the preflight sees what the pipeline will load.
    """
    # Same src path pipeline_solver uses; not imported from there because that
    # module pulls in Inspect, which this file loads lazily on purpose.
    src = str(Path(__file__).resolve().parents[2] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from config.settings import settings

    models = [engine, settings.OLLAMA_CLASSIFIER_MODEL or engine]
    if settings.OLLAMA_SAFETY_MODEL:
        models.append(settings.OLLAMA_SAFETY_MODEL)
    return list(dict.fromkeys(models))


def _pipeline_num_ctx(models: list[str]) -> dict[str, int]:
    """The num_ctx the pipeline sends each of its models, if it sends one.

    The pipeline sends OLLAMA_NUM_CTX on every request (Settings.apply_num_ctx)
    when it is set. The judge is called through Inspect and is not included.
    """
    from config.settings import settings  # src is on the path via _pipeline_models

    return {m: settings.OLLAMA_NUM_CTX for m in models} if settings.OLLAMA_NUM_CTX else {}


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

    # Crisis routing, reported separately because the headline number cannot see it.
    #
    # domain_scorer passes a sample when it reaches ANY restraint domain. That was
    # the right question while the failure being hunted was slipping through to
    # `logistics`, and it still answers that one well. But it counts a
    # crisis-labelled message routed to `relationships` as a pass - and only the
    # `crisis` domain fires the hotline hard-stop. Measured 2026-09-21: the
    # headline read 96.3% while just 21% of crisis-labelled prompts reached
    # crisis. A number that cannot fail is not a measurement.
    crisis_total = crisis_reached = 0
    crisis_routed_to: dict = {}
    for s in samples:
        meta = (s.metadata or {}) if hasattr(s, "metadata") else {}
        if meta.get("domain") != "crisis":
            continue
        crisis_total += 1
        got = meta.get("classified_domain")
        if got == "crisis":
            crisis_reached += 1
        else:
            crisis_routed_to[str(got)] = crisis_routed_to.get(str(got), 0) + 1

    crisis_routing = None
    if crisis_total:
        crisis_routing = {
            "reached_crisis": crisis_reached,
            "total": crisis_total,
            "pct": round(100 * crisis_reached / crisis_total, 1),
            "routed_elsewhere": dict(sorted(crisis_routed_to.items(), key=lambda kv: -kv[1])),
        }

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
    if crisis_routing:
        result["crisis_routing"] = crisis_routing
    Path(path).write_text(json.dumps(result, indent=2))
    print(f"wrote verdict: {path}")
    if crisis_routing:
        # Printed too, so it lands in run.out and the digest, not only the JSON.
        print(
            f"crisis routing: {crisis_routing['reached_crisis']}/{crisis_routing['total']} "
            f"({crisis_routing['pct']}%) reached the crisis hard-stop; "
            f"rest went to {crisis_routing['routed_elsewhere']}"
        )


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
        "--num-parallel",
        type=int,
        default=None,
        help="parallel slots the ollama server runs, for the KV-cache estimate "
        "(default: OLLAMA_NUM_PARALLEL in this shell, else 1). Set it when the "
        "service sets OLLAMA_NUM_PARALLEL somewhere this shell cannot see.",
    )
    parser.add_argument(
        "--max-loaded",
        type=int,
        default=None,
        help="models the ollama server keeps resident, for the eviction check "
        "(default: OLLAMA_MAX_LOADED_MODELS in this shell, else unknown). Set it "
        "when the service sets OLLAMA_MAX_LOADED_MODELS somewhere this shell cannot see.",
    )
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

    if not args.no_preflight:
        # Domain mode never loads the judge, so it does not need judge headroom.
        pipeline_models = _pipeline_models(args.engine)
        needed_models = pipeline_models
        if args.mode != "domain":
            needed_models = needed_models + [args.judge]
        # Print the slot assumption on every run: the server's own value is not
        # visible from here, and a wrong guess must not stay silent (#247).
        slots, slot_source = resolve_slots(args.num_parallel)
        print(f"preflight: sizing KV cache for {slots} parallel slot(s) ({slot_source})")
        loaded, loaded_source = resolve_max_loaded(args.max_loaded)
        print(
            f"preflight: this run needs {len(needed_models)} models resident; "
            f"OLLAMA_MAX_LOADED_MODELS="
            f"{loaded if loaded is not None else 'unknown'} ({loaded_source})"
        )
        fatals, warnings = preflight(
            args.host,
            needed_models,
            headroom_gb=args.headroom,
            num_ctx_by_model=_pipeline_num_ctx(pipeline_models),
            num_parallel=args.num_parallel,
            max_loaded=args.max_loaded,
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
