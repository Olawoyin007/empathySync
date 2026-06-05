#!/usr/bin/env python3
"""
Version consistency checker for empathySync.

Reads the authoritative version from pyproject.toml and verifies that
every other version-bearing file references the same version.

Usage:
    python scripts/check_version.py        # from repo root
    python scripts/check_version.py --fix  # show the fix commands too

Exit codes:
    0 — all files consistent
    1 — one or more mismatches found
"""

import re
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Extractors — each returns (found_version_string, error_message_or_None)
# ---------------------------------------------------------------------------


def read_pyproject_version():
    """Source of truth. Must exist and have a parseable version field."""
    path = ROOT / "pyproject.toml"
    if not path.exists():
        return None, "pyproject.toml not found"
    match = re.search(r'^version\s*=\s*"([^"]+)"', path.read_text(), re.MULTILINE)
    if not match:
        return None, "pyproject.toml: version field not found"
    return match.group(1), None


def read_settings_version():
    path = ROOT / "src" / "config" / "settings.py"
    if not path.exists():
        return None, "src/config/settings.py not found"
    match = re.search(r'APP_VERSION\s*:\s*str\s*=\s*"([^"]+)"', path.read_text())
    if not match:
        return None, "src/config/settings.py: APP_VERSION field not found"
    return match.group(1), None


def read_readme_version():
    path = ROOT / "README.md"
    if not path.exists():
        return None, "README.md not found"
    # Match the releases/tag/vX.Y.Z URL in the badge line — most canonical reference
    match = re.search(r"releases/tag/v([0-9]+\.[0-9]+(?:\.[0-9]+)?)", path.read_text())
    if not match:
        return None, "README.md: releases/tag badge URL not found"
    return match.group(1), None


def read_changelog_version():
    path = ROOT / "CHANGELOG.md"
    if not path.exists():
        return None, "CHANGELOG.md not found"
    # Find the first versioned header — skip [Unreleased]
    match = re.search(r"^## v([0-9]+\.[0-9]+(?:\.[0-9]+)?)", path.read_text(), re.MULTILINE)
    if not match:
        return None, "CHANGELOG.md: no versioned header found (e.g. '## v1.10.1')"
    return match.group(1), None


# ---------------------------------------------------------------------------
# Checks table — label, reader function, fix hint
# ---------------------------------------------------------------------------

CHECKS = [
    (
        "src/config/settings.py",
        read_settings_version,
        'Change APP_VERSION: str = "..." to match pyproject.toml',
    ),
    (
        "README.md",
        read_readme_version,
        "Update the release badge URL and tag link on line 12",
    ),
    (
        "CHANGELOG.md",
        read_changelog_version,
        "Rename the [Unreleased] header to ## v{version} (YYYY-MM-DD)",
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Check empathySync version consistency")
    parser.add_argument("--fix", action="store_true", help="Show fix hints for each failure")
    args = parser.parse_args()

    # Authoritative version
    canonical, err = read_pyproject_version()
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)

    print(f"Authoritative version (pyproject.toml): {canonical}\n")

    failures = []
    for label, reader, fix_hint in CHECKS:
        found, err = reader()
        if err:
            print(f"  FAIL  {label}")
            print(f"        {err}")
            failures.append((label, fix_hint))
        elif found != canonical:
            print(f"  FAIL  {label}")
            print(f"        found {found!r}, expected {canonical!r}")
            failures.append((label, fix_hint.format(version=canonical)))
        else:
            print(f"  OK    {label}  ({found})")

    print()

    if not failures:
        print("All version references consistent.")
        sys.exit(0)

    print(f"{len(failures)} file(s) out of sync.\n")

    if args.fix:
        print("Fix hints:")
        for label, hint in failures:
            print(f"  {label}: {hint}")
        print()

    print("Run with --fix to see fix hints.")
    sys.exit(1)


if __name__ == "__main__":
    main()
