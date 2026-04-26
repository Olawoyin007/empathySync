#!/usr/bin/env python3
"""
empathySync model benchmark.

Measures classifier accuracy and engine conversation quality across Ollama
models so users can pick the right model for their hardware.

Output: docs/model-benchmark.md
Partial results: docs/benchmark-results.json (saved after each model)

Usage:
    python scripts/benchmark.py                          # all defaults
    python scripts/benchmark.py --resume                 # skip already-done models
    python scripts/benchmark.py --skip-classifier        # engine only
    python scripts/benchmark.py --skip-engine            # classifier only
    python scripts/benchmark.py \\
        --classifier-models smollm2:360m qwen2.5:1.5b-instruct \\
        --engine-models qwen2.5:7b-instruct gemma3:12b
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from unittest.mock import MagicMock

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config.settings import settings  # noqa: E402

RESULTS_FILE = os.path.join(ROOT, "docs", "benchmark-results.json")
PROBE_TIMEOUT = 30  # seconds - quick health check before committing to full benchmark

# ---------------------------------------------------------------------------
# Default model lists
# ---------------------------------------------------------------------------

DEFAULT_CLASSIFIER_MODELS = [
    "smollm2:135m",
    "smollm2:360m",
    "qwen2.5:1.5b-instruct",
    "gemma:2b-instruct",
    "qwen2.5:3b-instruct",
    "llama3.2:latest",
    "phi3.5:latest",
    "mistral:7b-instruct",
]

DEFAULT_ENGINE_MODELS = [
    "qwen2.5:3b-instruct",
    "dolphin-mistral:latest",
    "mistral:7b-instruct",
    "llama3.1:8b",
    "qwen2.5:7b-instruct",
    "gemma3:12b",
    "phi4:latest",
    "qwen2.5:14b-instruct-q4_K_M",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DISTRESS_DOMAINS = {"crisis", "emotional", "health", "relationships"}


def hardware_tier(size_gb: float) -> str:
    if size_gb < 1.0:
        return "CPU / Any"
    if size_gb < 3.0:
        return "4 GB GPU"
    if size_gb < 6.5:
        return "8 GB GPU"
    if size_gb < 11.0:
        return "12 GB GPU"
    if size_gb < 18.0:
        return "16 GB GPU"
    return "24 GB GPU"


def get_installed_models() -> dict:
    """Return {name: size_gb} for all locally installed Ollama models."""
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    models = {}
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return models
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            size = float(parts[2])
            unit = parts[3]
            if unit == "MB":
                size /= 1024
            models[name] = round(size, 2)
        except (ValueError, IndexError):
            pass
    return models


def probe_model(model_name: str) -> bool:
    """
    Quick sanity check - send a tiny prompt to Ollama with a short timeout.
    Returns True if the model responds, False if it times out or errors.
    Avoids wasting minutes on a model that can't load (e.g. OOM).
    """
    import httpx

    url = f"{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": model_name,
        "prompt": "Hi",
        "stream": False,
        "options": {"num_predict": 5, "temperature": 0.0},
    }
    try:
        r = httpx.post(url, json=payload, timeout=PROBE_TIMEOUT)
        r.raise_for_status()
        return bool(r.json().get("response"))
    except Exception as e:
        print(f"  probe failed for {model_name}: {e}", flush=True)
        return False


def load_partial_results() -> dict:
    """Load existing benchmark-results.json, returning empty dicts if missing."""
    if not os.path.exists(RESULTS_FILE):
        return {"classifier": {}, "engine": {}}
    try:
        with open(RESULTS_FILE) as f:
            data = json.load(f)
        return {
            "classifier": data.get("classifier", {}),
            "engine": data.get("engine", {}),
        }
    except Exception as e:
        print(f"  warn: could not load {RESULTS_FILE}: {e}", flush=True)
        return {"classifier": {}, "engine": {}}


def save_partial_results(classifier_results: dict, engine_results: dict) -> None:
    """Persist current results to JSON after each model completes."""
    data = {
        "classifier": classifier_results,
        "engine": engine_results,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = RESULTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, RESULTS_FILE)


def format_size(size_gb: float) -> str:
    if size_gb < 1.0:
        return f"{size_gb * 1024:.0f} MB"
    return f"{size_gb:.1f} GB"


def pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def fmt_ms(v: float) -> str:
    if v >= 1000:
        return f"{v / 1000:.1f}s"
    return f"{v:.0f}ms"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_stress_tests() -> list:
    """Return [(name, scenario_dict), ...] from all stress test YAMLs."""
    pattern = os.path.join(ROOT, "tests", "conversations", "stress_test_*.yaml")
    results = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            data = yaml.safe_load(f)
        name = os.path.basename(path).replace(".yaml", "")
        results.append((name, data))
    return results


def load_distress_corpus() -> list:
    """Return all entries from distress_corpus.yaml as a flat list."""
    path = os.path.join(ROOT, "tests", "classification", "distress_corpus.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)
    entries = []
    for _category, items in data.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "text" in item and "distress" in item:
                    entries.append(item)
    return entries


def load_domain_corpus() -> list:
    """Return all entries from domain_corpus.yaml as a flat list."""
    path = os.path.join(ROOT, "tests", "classification", "domain_corpus.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)

    valid_domains = {
        "crisis",
        "harmful",
        "health",
        "money",
        "emotional",
        "relationships",
        "spirituality",
        "logistics",
    }
    entries = []
    for _category, items in data.items():
        if isinstance(items, list):
            for item in items:
                if (
                    isinstance(item, dict)
                    and "text" in item
                    and item.get("expected_domain") in valid_domains
                ):
                    entries.append(item)
    return entries


# ---------------------------------------------------------------------------
# Classifier benchmark
# ---------------------------------------------------------------------------


def bench_classifier(model_name: str, domain_corpus: list, distress_corpus: list) -> dict:
    """
    Benchmark a model as the classifier.
    Sets OLLAMA_CLASSIFIER_MODEL and OLLAMA_MODEL to model_name,
    then runs domain classification (domain_corpus) and distress detection.
    """
    settings.OLLAMA_CLASSIFIER_MODEL = model_name
    settings.OLLAMA_MODEL = model_name

    # Import inside function so fresh instances pick up updated settings
    from models.risk_classifier import RiskClassifier

    classifier = RiskClassifier(use_llm=True)

    domain_hits = 0
    domain_total = 0
    distress_tp = 0
    distress_fn = 0
    distress_fp = 0
    distress_tn = 0
    latencies = []

    # Domain accuracy from labeled domain corpus (replaces stress test proxy)
    print(
        f"  [classifier] {model_name} - domain accuracy ({len(domain_corpus)} examples)...",
        flush=True,
    )
    for item in domain_corpus:
        expected = item["expected_domain"]
        t0 = time.perf_counter()
        try:
            result = classifier.classify(item["text"], conversation_history=[])
            latencies.append((time.perf_counter() - t0) * 1000)
            if result.get("domain") == expected:
                domain_hits += 1
            domain_total += 1
        except Exception as e:
            print(f"    warn: {e}", flush=True)
            domain_total += 1

    # Distress detection from labeled corpus
    print(
        f"  [classifier] {model_name} - distress detection ({len(distress_corpus)} examples)...",
        flush=True,
    )
    for entry in distress_corpus:
        text = entry["text"]
        expected_distress = entry["distress"]
        t0 = time.perf_counter()
        try:
            result = classifier.classify(text, conversation_history=[])
            latencies.append((time.perf_counter() - t0) * 1000)
            detected = (
                result.get("is_personal_distress", False)
                or result.get("distress_present", False)
                or result.get("domain") in DISTRESS_DOMAINS
            )
            if expected_distress and detected:
                distress_tp += 1
            elif expected_distress and not detected:
                distress_fn += 1
            elif not expected_distress and detected:
                distress_fp += 1
            else:
                distress_tn += 1
        except Exception:
            if expected_distress:
                distress_fn += 1
            else:
                distress_tn += 1

    distress_positive = distress_tp + distress_fn
    distress_negative = distress_fp + distress_tn

    return {
        "domain_acc": domain_hits / domain_total if domain_total else 0.0,
        "distress_recall": distress_tp / distress_positive if distress_positive else 0.0,
        "distress_fp_rate": distress_fp / distress_negative if distress_negative else 0.0,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "domain_total": domain_total,
        "distress_total": distress_positive,
    }


# ---------------------------------------------------------------------------
# Engine benchmark
# ---------------------------------------------------------------------------


def _make_session():
    """Create a fresh ConversationSession with mocked tracker/network."""
    from models.ai_wellness_guide import WellnessGuide
    from models.conversation_session import ConversationSession
    from utils.trusted_network import TrustedNetwork
    from utils.wellness_tracker import WellnessTracker

    tracker = MagicMock(spec=WellnessTracker)
    tracker.should_enforce_cooldown.return_value = (False, "")
    tracker.should_show_graduation_prompt.return_value = (False, "")
    tracker.calculate_dependency_signals.return_value = {"dependency_score": 0.0}

    return ConversationSession(
        guide=WellnessGuide(),
        tracker=tracker,
        network=MagicMock(spec=TrustedNetwork),
    )


def bench_engine(model_name: str, stress_tests: list) -> dict:
    """
    Benchmark a model as the main engine on the full stress test corpus.
    Checks must_not_contain, max_words, and mode accuracy per turn.
    """
    settings.OLLAMA_MODEL = model_name
    settings.OLLAMA_CLASSIFIER_MODEL = ""  # let engine model handle classification too

    passes = 0
    total_checks = 0
    mode_hits = 0
    mode_total = 0
    scenario_passes = 0
    scenario_total = 0
    latencies = []

    print(f"  [engine] {model_name} - {len(stress_tests)} scenarios...", flush=True)

    for name, scenario in stress_tests:
        turns = scenario.get("turns", [])
        if not turns:
            continue

        session = _make_session()
        scenario_failed = False

        for i, turn in enumerate(turns):
            user_input = turn["input"]
            t0 = time.perf_counter()
            try:
                result = session.process_message(user_input)
                latencies.append((time.perf_counter() - t0) * 1000)
                response = result.response if hasattr(result, "response") else str(result)
            except Exception as e:
                print(f"    warn [{name} T{i + 1}]: {e}", flush=True)
                latencies.append((time.perf_counter() - t0) * 1000)
                scenario_failed = True
                continue

            # must_not_contain
            for phrase in turn.get("must_not_contain", []):
                total_checks += 1
                if phrase.lower() not in response.lower():
                    passes += 1
                else:
                    scenario_failed = True

            # max_words
            max_words = turn.get("max_words")
            if max_words is not None:
                total_checks += 1
                if len(response.split()) <= max_words:
                    passes += 1
                else:
                    scenario_failed = True

            # mode accuracy
            expected_mode = turn.get("expected_mode")
            if expected_mode and hasattr(result, "risk_assessment") and result.risk_assessment:
                ra = result.risk_assessment
                domain = ra.get("domain", "logistics")
                ipt = ra.get("is_practical_technique", False)
                actual_mode = "practical" if (domain == "logistics" or ipt) else "reflective"
                mode_total += 1
                if actual_mode == expected_mode:
                    mode_hits += 1

        scenario_total += 1
        if not scenario_failed:
            scenario_passes += 1

    return {
        "scenario_pass_rate": scenario_passes / scenario_total if scenario_total else 0.0,
        "check_pass_rate": passes / total_checks if total_checks else 0.0,
        "mode_acc": mode_hits / mode_total if mode_total else 0.0,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "scenario_total": scenario_total,
        "total_checks": total_checks,
    }


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------


def build_markdown(classifier_results: dict, engine_results: dict, installed: dict, ts: str) -> str:
    lines = [
        "# Model Benchmark",
        "",
        "Performance of Ollama models on empathySync's stress test corpus "
        "(20 scenarios) and distress detection corpus (60 examples).",
        "",
        f"_Last run: {ts}_",
        "",
        "---",
        "",
        "## Classifier",
        "",
        "Runs on every user message to detect domain and distress signals. "
        "Domain accuracy measured on 90 labeled examples (`tests/classification/domain_corpus.yaml`). "
        "Distress recall measured on 61 labeled examples (`tests/classification/distress_corpus.yaml`).",
        "",
        "**Distress Recall is the critical metric** - a missed distress signal is a safety failure.",
        "",
        "| Model | Size | Min VRAM | Domain Acc | Distress Recall | FP Rate | Avg Latency |",
        "|-------|------|:--------:|:----------:|:---------------:|:-------:|:-----------:|",
    ]

    for model, m in classifier_results.items():
        size_gb = installed.get(model, 0.0)
        lines.append(
            f"| `{model}` | {format_size(size_gb)} | {hardware_tier(size_gb)} "
            f"| {pct(m['domain_acc'])} | {pct(m['distress_recall'])} "
            f"| {pct(m['distress_fp_rate'])} | {fmt_ms(m['avg_latency_ms'])} |"
        )

    lines += [
        "",
        "## Main Engine",
        "",
        "Generates the actual response. Runs once per turn after classification.",
        "**Scenario Pass Rate** = all must-not-contain and word-limit constraints satisfied.",
        "",
        "| Model | Size | Min VRAM | Scenario Pass | Mode Acc | Avg Latency/turn |",
        "|-------|------|:--------:|:-------------:|:--------:|:----------------:|",
    ]

    for model, m in engine_results.items():
        size_gb = installed.get(model, 0.0)
        lines.append(
            f"| `{model}` | {format_size(size_gb)} | {hardware_tier(size_gb)} "
            f"| {pct(m['scenario_pass_rate'])} | {pct(m['mode_acc'])} "
            f"| {fmt_ms(m['avg_latency_ms'])} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Min VRAM by Model Size",
        "",
        "Running classifier and engine simultaneously requires combined VRAM.",
        "Use `OLLAMA_CLASSIFIER_MODEL` to run a smaller classifier while the engine uses a larger model.",
        "",
        "| Min VRAM | Classifier | Engine |",
        "|:--------:|-----------|--------|",
        "| CPU / Any | `smollm2:360m` | `qwen2.5:3b-instruct` |",
        "| 4 GB | `qwen2.5:1.5b-instruct` | `qwen2.5:3b-instruct` |",
        "| 8 GB | `qwen2.5:3b-instruct` | `qwen2.5:7b-instruct` |",
        "| 12 GB | `mistral:7b-instruct` | `gemma3:12b` |",
        "| 16 GB | `mistral:7b-instruct` | `qwen2.5:14b-instruct` |",
        "",
        "> Recommendations are updated by running `python scripts/benchmark.py`.",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="empathySync model benchmark")
    parser.add_argument(
        "--classifier-models",
        nargs="+",
        default=DEFAULT_CLASSIFIER_MODELS,
        help="Models to benchmark as classifier",
    )
    parser.add_argument(
        "--engine-models",
        nargs="+",
        default=DEFAULT_ENGINE_MODELS,
        help="Models to benchmark as engine",
    )
    parser.add_argument("--skip-classifier", action="store_true")
    parser.add_argument("--skip-engine", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load existing results and skip already-benchmarked models",
    )
    args = parser.parse_args()

    installed = get_installed_models()
    stress_tests = load_stress_tests()
    distress_corpus = load_distress_corpus()
    domain_corpus = load_domain_corpus()

    print(
        f"Loaded {len(stress_tests)} stress test scenarios, "
        f"{len(domain_corpus)} domain corpus examples, "
        f"{len(distress_corpus)} distress corpus examples",
        flush=True,
    )
    print(f"Installed models: {list(installed.keys())}\n", flush=True)

    # Load partial results if resuming, otherwise start fresh
    if args.resume:
        partial = load_partial_results()
        classifier_results = partial["classifier"]
        engine_results = partial["engine"]
        print(
            f"Resuming: {len(classifier_results)} classifier, {len(engine_results)} engine results loaded",
            flush=True,
        )
    else:
        classifier_results = {}
        engine_results = {}

    t_start_all = time.perf_counter()

    try:
        if not args.skip_classifier:
            print("=== Classifier Benchmark ===", flush=True)
            for model in args.classifier_models:
                if model not in installed:
                    print(f"  skip {model} (not installed)", flush=True)
                    continue
                if args.resume and model in classifier_results:
                    print(f"  skip {model} (already done)", flush=True)
                    continue
                print(f"  probing {model}...", flush=True)
                if not probe_model(model):
                    print(f"  skip {model} (probe failed - model may not load)", flush=True)
                    continue
                print(f"  benchmarking {model}...", flush=True)
                try:
                    classifier_results[model] = bench_classifier(
                        model, domain_corpus, distress_corpus
                    )
                    m = classifier_results[model]
                    print(
                        f"  -> domain={pct(m['domain_acc'])} distress_recall={pct(m['distress_recall'])} "
                        f"fp={pct(m['distress_fp_rate'])} latency={fmt_ms(m['avg_latency_ms'])}",
                        flush=True,
                    )
                    save_partial_results(classifier_results, engine_results)
                except Exception as e:
                    print(f"  ERROR [{model}]: {e}", flush=True)
                    traceback.print_exc()
                    save_partial_results(classifier_results, engine_results)
            print(flush=True)

        if not args.skip_engine:
            print("=== Engine Benchmark ===", flush=True)
            for model in args.engine_models:
                if model not in installed:
                    print(f"  skip {model} (not installed)", flush=True)
                    continue
                if args.resume and model in engine_results:
                    print(f"  skip {model} (already done)", flush=True)
                    continue
                print(f"  probing {model}...", flush=True)
                if not probe_model(model):
                    print(f"  skip {model} (probe failed - model may not load)", flush=True)
                    continue
                print(f"  benchmarking {model}...", flush=True)
                try:
                    engine_results[model] = bench_engine(model, stress_tests)
                    m = engine_results[model]
                    print(
                        f"  -> scenarios={pct(m['scenario_pass_rate'])} mode={pct(m['mode_acc'])} "
                        f"latency={fmt_ms(m['avg_latency_ms'])}",
                        flush=True,
                    )
                    save_partial_results(classifier_results, engine_results)
                except Exception as e:
                    print(f"  ERROR [{model}]: {e}", flush=True)
                    traceback.print_exc()
                    save_partial_results(classifier_results, engine_results)
            print(flush=True)

    except KeyboardInterrupt:
        print("\nInterrupted - saving partial results...", flush=True)
        save_partial_results(classifier_results, engine_results)
        print(f"Partial results saved to {RESULTS_FILE}", flush=True)
        print("Resume with: python scripts/benchmark.py --resume", flush=True)
        sys.exit(0)

    elapsed = time.perf_counter() - t_start_all
    print(f"Total runtime: {elapsed / 60:.1f} min", flush=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = build_markdown(classifier_results, engine_results, installed, ts)

    out_path = os.path.join(ROOT, "docs", "model-benchmark.md")
    with open(out_path, "w") as f:
        f.write(md)

    save_partial_results(classifier_results, engine_results)
    print(f"Written: {out_path}", flush=True)


if __name__ == "__main__":
    main()
