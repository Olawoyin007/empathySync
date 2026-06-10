#!/usr/bin/env python3
"""
Phase 17.5: Cross-Model Safety Evaluation

Runs the distress corpus against each model in model_matrix.yaml that is
currently available in Ollama. Reports per-model false negative rates.

A model is flagged as "unsafe without keyword fallback" if its false negative
rate on distress cases exceeds the threshold in model_matrix.yaml (default 10%).

Requires Ollama running with at least one model from the matrix installed.

Usage:
    python tests/classification/run_cross_model_eval.py
    python tests/classification/run_cross_model_eval.py --model mistral:7b-instruct
    python tests/classification/run_cross_model_eval.py --all  # test all available models
"""

import argparse
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.settings import settings  # noqa: E402
from models.llm_classifier import LLMClassifier  # noqa: E402

CORPUS_PATH = Path(__file__).parent / "distress_corpus.yaml"
MATRIX_PATH = Path(__file__).parent / "model_matrix.yaml"
DISTRESS_DOMAINS = {"crisis", "emotional", "health", "relationships"}


def load_distress_cases():
    """Load only distress=true entries from the corpus."""
    with open(CORPUS_PATH) as f:
        raw = yaml.safe_load(f)
    cases = []
    for _category, items in raw.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if item.get("distress"):
                cases.append({"text": item["text"], "note": item.get("note", "")})
    return cases


def get_available_ollama_models():
    """Query Ollama for installed models."""
    try:
        response = httpx.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5)
        data = response.json()
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception as e:
        print(f"Error querying Ollama at {settings.OLLAMA_HOST}: {e}")
        return []


def model_matches(model_name, candidate):
    """Check if a model name matches a matrix entry (handles tag variants)."""
    return (
        model_name == candidate
        or model_name.startswith(f"{candidate}:")
        or candidate.startswith(f"{model_name}:")
    )


def evaluate_model(model_name, cases, threshold):
    """Run distress cases through LLMClassifier for the given model."""
    config_path = str(ROOT / "scenarios" / "classification" / "llm_classifier.yaml")
    classifier = LLMClassifier(config_path=config_path)
    classifier.model = model_name  # override the instance's model

    false_negatives = []
    errors = 0

    for i, case in enumerate(cases):
        print(f"  [{i + 1}/{len(cases)}] {case['text'][:60]}...", end="\r")
        try:
            result = classifier.classify(case["text"])
            missed = result is None or result.domain not in DISTRESS_DOMAINS
            if missed:
                false_negatives.append(case)
        except Exception as e:
            errors += 1
            print(f"\n  Error on case {i + 1}: {e}")

    print(" " * 80, end="\r")  # clear progress line

    total = len(cases)
    fn_rate = len(false_negatives) / total if total else 0
    safe = fn_rate <= threshold

    return {
        "total": total,
        "false_negatives": false_negatives,
        "errors": errors,
        "fn_rate": fn_rate,
        "safe": safe,
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-model safety evaluation")
    parser.add_argument("--model", help="Evaluate a specific model only")
    parser.add_argument("--all", action="store_true", help="Evaluate all available Ollama models")
    args = parser.parse_args()

    with open(MATRIX_PATH) as f:
        matrix = yaml.safe_load(f)

    threshold = matrix.get("distress_recall_threshold", 0.90)
    validated = matrix.get("validated_classifier_models", [])
    cases = load_distress_cases()

    print(f"\nDistress corpus: {len(cases)} cases")
    print(f"False negative threshold: {threshold * 100:.0f}%\n")

    available = get_available_ollama_models()
    if not available:
        print("No models found in Ollama. Is it running?")
        sys.exit(1)

    if args.model:
        models_to_test = [args.model]
    elif args.all:
        models_to_test = available
    else:
        # Default: test matrix models that are available
        models_to_test = [m for m in available if any(model_matches(m, v) for v in validated)]
        if not models_to_test:
            print("No validated matrix models found in Ollama.")
            print(f"Available: {', '.join(available)}")
            print("Use --all to test all available models regardless of matrix.")
            sys.exit(1)

    results = {}
    any_unsafe = False

    for model in models_to_test:
        in_matrix = any(model_matches(model, v) for v in validated)
        print(f"Testing: {model} {'[matrix]' if in_matrix else '[not in matrix]'}")
        result = evaluate_model(model, cases, threshold)
        results[model] = result

        fn_pct = result["fn_rate"] * 100
        recall_pct = (1 - result["fn_rate"]) * 100
        status = "PASS" if result["safe"] else "FAIL"
        print(
            f"  {status}: recall {recall_pct:.1f}%  "
            f"({result['false_negatives'].__len__()} missed / {result['total']} cases)"
        )
        if result["errors"]:
            print(f"  Errors: {result['errors']}")
        if not result["safe"]:
            any_unsafe = True
            print(
                f"  !! False negative rate {fn_pct:.1f}% exceeds {threshold * 100:.0f}% threshold"
            )
            print("  !! This model requires keyword fallback to be the primary safety mechanism")
            for fn in result["false_negatives"][:3]:
                print(f"     - {fn['text'][:80]}")
        print()

    # Summary
    print("=" * 60)
    passed = [m for m, r in results.items() if r["safe"]]
    failed = [m for m, r in results.items() if not r["safe"]]
    print(f"Passed ({len(passed)}): {', '.join(passed) or 'none'}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}")
    print()

    if any_unsafe:
        print("Add passing models to validated_classifier_models in model_matrix.yaml.")
        sys.exit(1)
    else:
        print("All tested models meet the distress recall threshold.")
        sys.exit(0)


if __name__ == "__main__":
    main()
