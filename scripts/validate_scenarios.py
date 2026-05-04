#!/usr/bin/env python3
"""
Validate scenario YAML files for required structure.

Checks:
  - All domain files have required fields (domain, risk_weight, triggers, response_rules)
  - crisis.yaml has crisis_response
  - harmful.yaml has refusal_response
  - No duplicate triggers across domain files (ambiguous classification)

Usage:
  python scripts/validate_scenarios.py
  python scripts/validate_scenarios.py --domains-dir scenarios/domains
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["domain", "risk_weight", "triggers", "response_rules"]
SPECIAL_FIELDS = {
    "crisis.yaml": "crisis_response",
    "harmful.yaml": "refusal_response",
}


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_domain_file(path: Path, data: dict) -> list[str]:
    errors = []
    name = path.name

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{path}: missing required field '{field}'")
        elif field == "triggers" and not isinstance(data[field], list):
            errors.append(f"{path}: 'triggers' must be a list, got {type(data[field]).__name__}")
        elif field == "response_rules" and not isinstance(data[field], list):
            errors.append(
                f"{path}: 'response_rules' must be a list, got {type(data[field]).__name__}"
            )

    if name in SPECIAL_FIELDS:
        special = SPECIAL_FIELDS[name]
        if special not in data:
            errors.append(f"{path}: missing required field '{special}'")

    return errors


def find_duplicate_triggers(domain_files: list[tuple[Path, dict]]) -> list[str]:
    trigger_map: dict[str, list[str]] = defaultdict(list)
    for path, data in domain_files:
        for trigger in data.get("triggers", []):
            trigger_map[trigger.lower().strip()].append(path.name)

    errors = []
    for trigger, files in trigger_map.items():
        if len(files) > 1:
            errors.append(
                f"Duplicate trigger '{trigger}' found in: {', '.join(sorted(set(files)))}"
            )
    return errors


def main(domains_dir: Path) -> int:
    if not domains_dir.is_dir():
        print(f"ERROR: domains directory not found: {domains_dir}", file=sys.stderr)
        return 1

    domain_files = sorted(domains_dir.glob("*.yaml"))
    if not domain_files:
        print(f"ERROR: no YAML files found in {domains_dir}", file=sys.stderr)
        return 1

    all_errors = []
    loaded = []

    for path in domain_files:
        try:
            data = load_yaml(path)
        except yaml.YAMLError as e:
            all_errors.append(f"{path}: YAML parse error - {e}")
            continue

        errors = validate_domain_file(path, data)
        all_errors.extend(errors)
        loaded.append((path, data))

    all_errors.extend(find_duplicate_triggers(loaded))

    if all_errors:
        print(f"YAML validation failed - {len(all_errors)} error(s):\n")
        for error in all_errors:
            print(f"  {error}")
        return 1

    print(f"OK - {len(domain_files)} domain file(s) validated, no errors found.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate scenario YAML files.")
    parser.add_argument(
        "--domains-dir",
        type=Path,
        default=Path(__file__).parent.parent / "scenarios" / "domains",
        help="Path to the domains directory (default: scenarios/domains)",
    )
    args = parser.parse_args()
    sys.exit(main(args.domains_dir))
