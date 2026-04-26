#!/usr/bin/env python3
"""
empathySync domain classification eval.

Runs the labeled domain corpus through RiskClassifier and reports accuracy
per domain. Mirrors intentKeeper's eval/run_eval.py for consistency.

Usage:
    python tests/classification/run_domain_eval.py
    python tests/classification/run_domain_eval.py --verbose
    python tests/classification/run_domain_eval.py --filter relationships
    python tests/classification/run_domain_eval.py --no-llm   # keyword only

Run from the repo root.
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS_PATH = Path(__file__).parent / "domain_corpus.yaml"

VALID_DOMAINS = {
    "crisis",
    "harmful",
    "health",
    "money",
    "emotional",
    "relationships",
    "spirituality",
    "logistics",
}


def load_corpus(filter_domain: str | None = None) -> list[dict]:
    with open(CORPUS_PATH) as f:
        data = yaml.safe_load(f)

    entries = []
    for category, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and "text" in item and "expected_domain" in item:
                if item["expected_domain"] not in VALID_DOMAINS:
                    continue
                if filter_domain and item["expected_domain"] != filter_domain:
                    continue
                entries.append(item)
    return entries


def run(corpus: list[dict], verbose: bool, use_llm: bool) -> dict:
    from models.risk_classifier import RiskClassifier

    classifier = RiskClassifier(use_llm=use_llm)

    total = len(corpus)
    correct = 0
    per_domain: dict = defaultdict(lambda: {"total": 0, "correct": 0})
    wrong = []

    print(f"\nRunning {total} examples (llm={'on' if use_llm else 'off'})...\n")

    for item in corpus:
        text = item["text"]
        expected = item["expected_domain"]
        note = item.get("note", "")

        result = classifier.classify(text, conversation_history=[])
        got = result.get("domain", "unknown")
        is_correct = got == expected

        per_domain[expected]["total"] += 1
        if is_correct:
            correct += 1
            per_domain[expected]["correct"] += 1
        else:
            wrong.append({"text": text, "expected": expected, "got": got, "note": note})

        if verbose:
            status = "OK" if is_correct else "FAIL"
            print(f"  {status:4} [{expected:>14}] -> [{got:<14}] {text[:55]}")

    pct = correct / total * 100 if total else 0
    print(f"\n{'─' * 60}")
    print(f"  Overall accuracy: {correct}/{total}  ({pct:.0f}%)")
    print(f"{'─' * 60}\n")

    print(f"  {'Domain':<16} {'Correct':>7}  {'Total':>5}  {'Acc':>5}")
    print(f"  {'─' * 16}  {'─' * 7}  {'─' * 5}  {'─' * 5}")
    for domain in sorted(per_domain):
        counts = per_domain[domain]
        t = counts["total"]
        c = counts["correct"]
        acc = c / t * 100 if t else 0
        bar = "#" * c + "." * (t - c)
        print(f"  {domain:<16} {c:>7}  {t:>5}  {acc:>4.0f}%  {bar}")

    if wrong:
        print(f"\n  Misclassified ({len(wrong)}):\n")
        for w in wrong:
            print(f"  expected: {w['expected']}")
            print(f"  got:      {w['got']}")
            print(f"  text:     {w['text'][:80]}")
            if w["note"]:
                print(f"  note:     {w['note']}")
            print()

    return {
        "accuracy": correct / total if total else 0.0,
        "correct": correct,
        "total": total,
        "per_domain": {
            d: counts["correct"] / counts["total"]
            for d, counts in per_domain.items()
            if counts["total"] > 0
        },
    }


def main():
    parser = argparse.ArgumentParser(description="empathySync domain classification eval")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--filter", metavar="DOMAIN", help="Only run examples for this domain")
    parser.add_argument("--no-llm", action="store_true", help="Use keyword classifier only")
    args = parser.parse_args()

    corpus = load_corpus(filter_domain=args.filter)
    if not corpus:
        print(f"No examples found (filter={args.filter!r})")
        sys.exit(1)

    run(corpus, verbose=args.verbose, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
