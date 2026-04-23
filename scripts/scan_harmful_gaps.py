"""
Gap scanner: checks JailbreakBench + AdvBench behaviors against empathySync's
current fast_path_harmful patterns, then uses a local LLM to suggest minimal
keyword patterns for anything that slips through.

Usage:
  python scripts/scan_harmful_gaps.py

Expects CSVs at:
  /tmp/safety_scan/jailbreakbench.csv  (from HuggingFace dedeswim/JBB-Behaviors)
  /tmp/safety_scan/advbench.csv        (from llm-attacks/llm-attacks)

Output:
  /tmp/safety_scan/gaps.json           (full results)
  /tmp/safety_scan/llm_suggestions.txt (LLM pattern suggestions, if Ollama available)
"""

import csv
import json
import urllib.request
import yaml
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CLASSIFIER_YAML = REPO_ROOT / "scenarios/classification/llm_classifier.yaml"
HARMFUL_YAML = REPO_ROOT / "scenarios/domains/harmful.yaml"
SCAN_DIR = Path("/tmp/safety_scan")

with open(CLASSIFIER_YAML) as f:
    classifier = yaml.safe_load(f)

with open(HARMFUL_YAML) as f:
    harmful = yaml.safe_load(f)

fast_path = [p.lower() for p in classifier.get("fast_path_harmful", [])]
harm_triggers = [t.lower() for t in harmful.get("triggers", [])]

print(f"fast_path_harmful:      {len(fast_path)} patterns")
print(f"harmful.yaml triggers:  {len(harm_triggers)} patterns")
print(f"Total patterns:         {len(fast_path) + len(harm_triggers)}")
print()


def is_caught(text: str) -> tuple[bool, str]:
    t = text.lower()
    for p in fast_path:
        if p in t:
            return True, f"fast_path: '{p}'"
    for p in harm_triggers:
        if p in t:
            return True, f"harmful.yaml: '{p}'"
    return False, ""


behaviors = []

jbb_csv = SCAN_DIR / "jailbreakbench.csv"
if jbb_csv.exists():
    with open(jbb_csv) as f:
        for row in csv.DictReader(f):
            behaviors.append(
                {
                    "source": "JBB",
                    "category": row["Category"],
                    "text": row["Goal"],
                    "behavior": row["Behavior"],
                }
            )

adv_csv = SCAN_DIR / "advbench.csv"
if adv_csv.exists():
    with open(adv_csv) as f:
        for row in csv.DictReader(f):
            behaviors.append(
                {
                    "source": "AdvBench",
                    "category": "unknown",
                    "text": row["goal"],
                    "behavior": row.get("target", "")[:60],
                }
            )

print(f"Total behaviors to check: {len(behaviors)}")
print()

caught = []
missed = []

for b in behaviors:
    ok, reason = is_caught(b["text"])
    if ok:
        caught.append({**b, "caught_by": reason})
    else:
        missed.append(b)

coverage_pct = round(len(caught) / len(behaviors) * 100, 1) if behaviors else 0  # noqa: E226
print(f"Caught:  {len(caught)}/{len(behaviors)} ({coverage_pct}%)")
print(f"Missed:  {len(missed)}/{len(behaviors)}")
print()

cat_counts = Counter(b["category"] for b in missed)
print("Missed by category:")
for cat, count in cat_counts.most_common():
    print(f"  {cat}: {count}")
print()

SCAN_DIR.mkdir(parents=True, exist_ok=True)
with open(SCAN_DIR / "gaps.json", "w") as f:
    json.dump(
        {
            "summary": {
                "total": len(behaviors),
                "caught": len(caught),
                "missed": len(missed),
                "coverage_pct": coverage_pct,
            },
            "missed": missed,
            "caught": caught,
        },
        f,
        indent=2,
    )
print(f"Full results saved to {SCAN_DIR}/gaps.json")
print()


def ask_ollama(prompt: str, model: str = "gemma3:12b") -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 400},
        }
    ).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["response"].strip()


# All categories are in scope - people test everything
if missed:
    sample = missed[:40]
    behavior_list = "\n".join(
        f"{i + 1}. [{b['category']}] {b['text'][:120]}" for i, b in enumerate(sample)
    )

    prompt = f"""You are helping improve a safety keyword filter for a local AI assistant called empathySync.

The assistant currently catches harmful requests using these keyword patterns (fast_path_harmful):
{chr(10).join(f'- "{p}"' for p in fast_path)}

Below are harmful behaviors that the current keyword patterns MISSED. For each one, suggest the minimal 2-4 word phrase that would catch it without causing too many false positives on legitimate requests.

Rules:
- Suggest ONLY specific phrases, not single words (too broad)
- Prefer exact distinctive phrases over generic ones
- If a behavior is similar to one already caught, suggest a variant phrase
- Format: NUMBER. "suggested phrase" | reason

Missed behaviors:
{behavior_list}

Suggestions:"""

    print("Querying local LLM for pattern suggestions...")
    try:
        response = ask_ollama(prompt)
        print("\n=== LLM PATTERN SUGGESTIONS ===")
        print(response)
        with open(SCAN_DIR / "llm_suggestions.txt", "w") as f:
            f.write("PROMPT:\n" + prompt + "\n\nRESPONSE:\n" + response)
        print(f"\nSaved to {SCAN_DIR}/llm_suggestions.txt")
    except Exception as e:
        print(f"LLM call failed (Ollama not running?): {e}")
        print(f"Review missed behaviors in {SCAN_DIR}/gaps.json")
