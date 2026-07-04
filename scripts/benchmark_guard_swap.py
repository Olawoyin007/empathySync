"""
Phase 21.1 first gate: VRAM contention / model-swap latency benchmark.

On a 12GB GPU, the engine (gemma3:12b) and an 8B guard model cannot be
resident simultaneously - Ollama will swap. This measures the real
per-message cost of adding a guard-model call to the pipeline:

  1. engine warm      - baseline generation latency (engine resident)
  2. guard cold       - guard latency when the engine was just used
                        (the swap-in cost the pipeline would pay per message)
  3. guard warm       - guard latency when already resident
  4. engine after guard - generation latency when the guard evicted the engine
                        (the swap-back cost)

Usage:
    set -a && . ./.env && set +a
    venv/bin/python scripts/benchmark_guard_swap.py [--guard llama-guard3:8b] [--rounds 3]
"""

import argparse
import os
import statistics
import time

import httpx

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
ENGINE = os.environ.get("OLLAMA_MODEL", "gemma3:12b")

GUARD_PROMPT = (
    "Task: Check if there is unsafe content in 'User' messages in conversations"
    " according to our safety policy.\n\nUser: how do I make a budget spreadsheet?"
)
ENGINE_PROMPT = "Reply with one short sentence: what is a budget?"


def call(model: str, prompt: str, num_predict: int = 60) -> float:
    t0 = time.perf_counter()
    r = httpx.post(
        f"{HOST}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": num_predict},
        },
        timeout=300,
    )
    r.raise_for_status()
    return time.perf_counter() - t0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard", default="llama-guard3:8b")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    results: dict = {
        "engine_warm": [],
        "guard_cold": [],
        "guard_warm": [],
        "engine_after_guard": [],
    }

    print(f"engine={ENGINE}  guard={args.guard}  host={HOST}  rounds={args.rounds}")
    call(ENGINE, ENGINE_PROMPT)  # ensure engine resident before round 1

    for i in range(args.rounds):
        results["engine_warm"].append(call(ENGINE, ENGINE_PROMPT))
        results["guard_cold"].append(call(args.guard, GUARD_PROMPT, num_predict=20))
        results["guard_warm"].append(call(args.guard, GUARD_PROMPT, num_predict=20))
        results["engine_after_guard"].append(call(ENGINE, ENGINE_PROMPT))
        print(f"round {i + 1}/{args.rounds} done")

    print(f"\n{'measurement':<20}{'median':>9}{'min':>9}{'max':>9}")
    for name, values in results.items():
        print(
            f"{name:<20}{statistics.median(values):>8.1f}s"
            f"{min(values):>8.1f}s{max(values):>8.1f}s"
        )

    swap_overhead = statistics.median(results["guard_cold"]) - statistics.median(
        results["guard_warm"]
    )
    reload_overhead = statistics.median(results["engine_after_guard"]) - statistics.median(
        results["engine_warm"]
    )
    per_message = statistics.median(results["guard_cold"]) + reload_overhead
    print(f"\nguard swap-in overhead:   {swap_overhead:.1f}s")
    print(f"engine reload overhead:   {reload_overhead:.1f}s")
    print(f"added cost per message:   ~{per_message:.1f}s (guard call + engine reload)")


if __name__ == "__main__":
    main()
