"""
Re-measure the oblique-crisis figure in docs/model-benchmark.md.

That table reports how many oblique-ideation messages reach the crisis hard stop
with the LLM classifier on, against intense-but-not-suicidal controls that must
not be escalated. It was measured by hand on 2026-09-16 and no script existed to
re-run it, so the number could not be checked against a later pipeline - and the
crisis second pass (#212) changed the pipeline underneath it.

This runs the same two sets from tests/classification/crisis_triage_corpus.yaml
twice: once with the keyword floor alone (use_llm=False) and once with the full
classifier (use_llm=True). The split is the point.

READ THIS BEFORE QUOTING THE NUMBER. The six oblique samples are the samples the
floor's trigger phrases were written from (#203, measured against the 32 controls
before inclusion). The floor therefore catches all six, and a headline "6 / 6"
says only that it covers its own source examples - it is trained-on-test and is
not evidence the oblique-crisis gap is closed. Its real job is as a regression
guard, which is how tests/classification/test_crisis_triage.py uses it.

The figure that is not trained-on is crisis recall against the 490-sample
adversarial corpus: 57.0%, up from 27.9% after the crisis second pass (#212).
Issue #218 tracks the 43% still missed.

Usage:
    set -a && . ./.env && set +a
    venv/bin/python scripts/eval_oblique_crisis.py
    venv/bin/python scripts/eval_oblique_crisis.py --classifier qwen2.5:14b-instruct-q4_K_M
    venv/bin/python scripts/eval_oblique_crisis.py --no-guard   # shipped default

Report the classifier and the guard state with any number this prints. The
optional safety guard escalates legal adult work to harmful, so a figure without
that state next to it cannot be compared to anything.
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests/classification/crisis_triage_corpus.yaml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", help="override OLLAMA_CLASSIFIER_MODEL")
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="unset OLLAMA_SAFETY_MODEL, which is the shipped default",
    )
    parser.add_argument("--verbose", action="store_true", help="print every sample")
    args = parser.parse_args()

    if args.classifier:
        os.environ["OLLAMA_CLASSIFIER_MODEL"] = args.classifier
    if args.no_guard:
        # Set empty rather than delete. config.settings calls load_dotenv() at
        # import, and load_dotenv does not overwrite a variable that is already
        # present - but a deleted one is absent, so .env puts the guard straight
        # back and the run silently measures a configuration you did not ask for.
        os.environ["OLLAMA_SAFETY_MODEL"] = ""

    from config.settings import settings
    from models.risk_classifier import RiskClassifier
    from utils.scenario_loader import ScenarioLoader

    corpus = yaml.safe_load(open(CORPUS))
    oblique = corpus["oblique_ideation"]
    benign = corpus["intense_benign"]

    loader = ScenarioLoader(str(ROOT / "scenarios"))
    floor_only = RiskClassifier(loader, use_llm=False)
    classifier = RiskClassifier(loader, use_llm=True)

    model = settings.OLLAMA_CLASSIFIER_MODEL or settings.OLLAMA_MODEL
    guard = settings.OLLAMA_SAFETY_MODEL or "unset"
    print(f"\nclassifier: {model}   guard: {guard}   num_ctx: {settings.OLLAMA_NUM_CTX}")
    print(f"corpus: {CORPUS.name} ({len(oblique)} oblique, {len(benign)} benign)\n")

    reached, by_floor, missed = 0, 0, []
    for entry in oblique:
        floor_domain = floor_only.classify(entry["text"], [])["domain"]
        domain = classifier.classify(entry["text"], [])["domain"]
        if floor_domain == "crisis":
            by_floor += 1
        if domain == "crisis":
            reached += 1
        else:
            missed.append((domain, entry["note"], entry["text"]))
        if args.verbose:
            via = "floor" if floor_domain == "crisis" else "classifier"
            mark = "OK  " if domain == "crisis" else "MISS"
            print(f"  {mark} [{domain:<13}] via {via:<10} {entry['note']}")

    escalated = []
    for entry in benign:
        domain = classifier.classify(entry["text"], [])["domain"]
        if domain == "crisis":
            escalated.append((entry["note"], entry["text"]))
        if args.verbose:
            print(f"  {'FP  ' if domain == 'crisis' else 'ok  '} [{domain:<13}] {entry['note']}")

    print(f"\n{'─' * 60}")
    print(f"  Oblique crisis reached:     {reached} / {len(oblique)}")
    print(f"    of which the floor alone: {by_floor} / {len(oblique)}  <- trained on these")
    print(f"    the classifier adds:      {reached - by_floor} / {len(oblique)}")
    print(f"  Benign wrongly escalated:   {len(escalated)} / {len(benign)}")
    print(f"{'─' * 60}")
    if by_floor == len(oblique):
        print(
            "\n  The floor catches all of them, so this run says nothing about the\n"
            "  classifier. These six are the floor's own source examples (#203).\n"
            "  For an untrained figure use crisis recall on the 490 corpus."
        )
    print()

    if missed:
        print("Missed:")
        for domain, note, text in missed:
            print(f"  -> {domain:<13} {note}\n     {text[:78]}")
        print()
    if escalated:
        print("Wrongly escalated:")
        for note, text in escalated:
            print(f"  -> {note}\n     {text[:78]}")
        print()


if __name__ == "__main__":
    main()
