"""Run the restraint eval: preflight, then a memory-safe, resumable eval_set.

Usage:
    python -m evals.empathysync_restraint.run                 # restraint side (judge)
    python -m evals.empathysync_restraint.run --mode domain   # classifier side (no judge)
    python -m evals.empathysync_restraint.run --mode bare     # ablation: no pipeline
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
from datetime import datetime, timezone
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


def _logs_not_produced_by_this_run(logs, started_at) -> list[str]:
    """Names of returned logs that finished before this invocation began.

    `eval_set` resumes from its log directory, which is the point: a Ctrl-C'd run
    picks up where it stopped. But when the directory already holds a *complete*
    run, nothing executes and it still prints "Completed all tasks successfully"
    and returns that older log. The score on screen is then the previous run's,
    under whatever engine, guard and corpus it used.

    That is a silent no-op dressed as a pass, in the harness the project's
    headline numbers come from, so it gets named rather than trusted. Measured on
    2026-11-18: a restraint run "succeeded" in under a second having scored
    nothing.
    """
    stale = []
    for log in logs or []:
        completed = getattr(getattr(log, "stats", None), "completed_at", None)
        if not completed:
            continue
        try:
            finished = datetime.fromisoformat(str(completed))
        except ValueError:
            continue
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        if finished < started_at:
            name = getattr(getattr(log, "eval", None), "task", "?")
            stale.append(f"{name} (finished {completed})")
    return stale


def _write_verdict(logs, path: str, mode: str, dataset: str, grade: str = "restraint") -> None:
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

    # The two practical failure directions, reported apart. The headline counts a
    # sample wrong either way, but "never did the task" and "did it, then pushed
    # the user off" call for different fixes, so a single number hides the one
    # that matters. Same reasoning as crisis_routing above.
    practical_split = None
    if grade == "practical":
        not_done = asked = pressured = 0
        for s in samples:
            sc = next(iter((s.scores or {}).values()), None)
            md = (sc.metadata if sc else {}) or {}
            if sc is None or sc.value != INCORRECT:
                continue
            if md.get("clarifying_only"):
                asked += 1
            elif not md.get("did_task"):
                not_done += 1
            elif md.get("exit_pressure"):
                pressured += 1
        practical_split = {
            "task_not_done": not_done,
            "asked_instead": asked,
            "needless_exit_pressure": pressured,
            "total": total,
        }

    result = {
        "eval": f"empathysync-{mode}" + ("-practical" if grade == "practical" else ""),
        "eval_version": os.environ.get("EVAL_VERSION", "dev"),
        "dataset": dataset,
        "dataset_hash": hashlib.sha256(Path(dataset).read_bytes()).hexdigest()[:12],
        "score_pct": score_pct,
        "correct": correct,
        "total": total,
        "errors": errors,
        "failed_checks": failed,
    }
    if practical_split:
        result["practical_split"] = practical_split
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
        choices=["restraint", "domain", "bare"],
        default="restraint",
        help="restraint = judge grades the response; domain = rule-based classifier "
        "check (no judge); bare = the same engine with no pipeline, graded by the "
        "same judge, so the difference from restraint mode is what the architecture adds",
    )
    parser.add_argument(
        "--grade",
        choices=["restraint", "practical"],
        default="restraint",
        help="which rubric the judge applies. restraint = did it hold back "
        "(the adversarial corpus); practical = did ordinary help survive, "
        "graded on whether the task got done and whether the reply added "
        "needless exit pressure (the practical corpus)",
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
    parser.add_argument(
        "--engine-temperature",
        type=float,
        default=0.0,
        help="decoding temperature for the engine (default 0.0, greedy, reproducible). "
        "The product ships 0.7; pass it to measure the shipped configuration, and read "
        "the result as one sample rather than a fixed figure - at 0.7 the replies are "
        "regenerated every run",
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

    # Domain mode grades the classified domain with no judge at all, so there is
    # no rubric for it to apply. Fail loudly rather than silently ignoring it.
    if args.grade == "practical" and args.mode == "domain":
        print(
            "--grade practical needs a judge; domain mode has none. Use --mode "
            "restraint (pipeline arm) or --mode bare (ceiling arm)."
        )
        return 1

    # Each mode is a different task; keep their logs apart so eval_set resume
    # never crosses them. Restraint mode keeps its existing logs/restraint path.
    if args.log_dir is None:
        # One directory per mode. Inspect's eval_set resumes from the log dir, so
        # two modes sharing one would resume each other's samples.
        by_mode = {
            "restraint": DEFAULT_LOG_DIR,
            "domain": DEFAULT_LOG_DIR.parent / "domain",
            "bare": DEFAULT_LOG_DIR.parent / "bare",
        }
        chosen = by_mode[args.mode]
        if args.grade == "practical":
            # A practical run and a restraint run of the same mode share a task
            # name; one log dir would make eval_set resume the other's samples.
            chosen = chosen.parent / f"practical-{args.mode}"
        args.log_dir = str(chosen)

    if not args.no_preflight:
        # Each mode loads a different set, and sizing for models a mode never
        # loads refuses runs that would have fit. Domain mode never loads the
        # judge. Bare mode runs no pipeline at all, so it loads neither the
        # classifier nor the safety guard - only the engine it prompts directly
        # and the judge that grades it.
        pipeline_models = _pipeline_models(args.engine)
        if args.mode == "bare":
            needed_models = [args.engine, args.judge]
            pipeline_models = [args.engine]
        elif args.mode == "domain":
            needed_models = pipeline_models
        else:
            needed_models = pipeline_models + [args.judge]
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

    from .task import empathysync_bare, empathysync_domain, empathysync_restraint

    if args.mode == "domain":
        the_task = empathysync_domain(
            dataset_path=args.dataset, engine=args.engine, ollama_host=args.host
        )
        grader = "rule-based (no judge)"
    elif args.mode == "bare":
        the_task = empathysync_bare(
            dataset_path=args.dataset,
            engine=args.engine,
            judge=args.judge,
            ollama_host=args.host,
            temperature=args.engine_temperature,
            grade=args.grade,
        )
        grader = args.judge
        print(
            "bare mode: no empathySync pipeline. Compare against a restraint-mode run\n"
            "           on the same dataset and judge; the gap is what the\n"
            "           architecture adds, not what the model does on its own."
        )
    else:
        the_task = empathysync_restraint(
            dataset_path=args.dataset,
            engine=args.engine,
            judge=args.judge,
            ollama_host=args.host,
            temperature=args.engine_temperature,
            grade=args.grade,
        )
        grader = args.judge

    print(
        f"mode={args.mode}  engine={args.engine}  grader={grader}  host={args.host}\n"
        f"engine_temperature={args.engine_temperature}"
        + (
            "  (greedy, reproducible)"
            if args.engine_temperature == 0.0
            else "  (SAMPLED - one sample, not a fixed figure)"
        )
        + "\n"
        f"dataset={args.dataset}\nlog_dir={args.log_dir}  "
        f"(Ctrl-C is safe; re-run the same command to resume)"
    )

    run_started = datetime.now(timezone.utc)
    success, logs = eval_set(
        tasks=[the_task],
        log_dir=args.log_dir,
        max_connections=args.max_connections,
        max_samples=1,
        limit=args.limit,
        retry_attempts=3,
    )

    stale = _logs_not_produced_by_this_run(logs, run_started)
    if stale:
        print(
            "\n"
            "!! NOTHING WAS MEASURED. eval_set found a complete run already in\n"
            f"!! {args.log_dir} and resumed into a no-op, so the result above is\n"
            "!! an older run's, under whatever engine, guard and corpus it used:\n"
            + "".join(f"!!   {s}\n" for s in stale)
            + "!! Use a fresh --log-dir to actually run the corpus.\n"
        )

    print(
        f"\nDone. success={success}. Browse results with:\n  inspect view --log-dir {args.log_dir}"
    )

    if args.result_json:
        try:
            _write_verdict(logs, args.result_json, args.mode, args.dataset, args.grade)
        except Exception as e:  # a verdict-file problem must never fail the eval
            print(f"WARNING: could not write verdict json: {e}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
