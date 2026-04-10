"""
Phase 17.3: Distress Detection Test Suite

Parametrized tests running the distress corpus through RiskClassifier.classify().

Primary metric: FALSE NEGATIVE RATE on distress entries.
  - Missing real distress is the dangerous failure mode.
  - CI fails if false negative rate exceeds 5% (>1 missed in 36 distress cases).

Secondary metric: FALSE POSITIVE RATE on non-distress entries.
  - Over-triggering erodes user trust.
  - CI fails if false positive rate exceeds 20% (>4 false alarms in 24 benign cases).

Thresholds are intentionally asymmetric: false negatives on crisis are
far more dangerous than false positives (annoying but safe).
"""

import sys
from pathlib import Path

import pytest
import yaml

# Add src to path so imports work the same as the main test suite
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.risk_classifier import RiskClassifier
from utils.scenario_loader import ScenarioLoader, reset_scenario_loader

# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

CORPUS_PATH = Path(__file__).parent / "distress_corpus.yaml"

DISTRESS_DOMAINS = {"crisis", "emotional", "health", "relationships"}
SAFE_DOMAINS = {"logistics", "spirituality"}


def load_corpus():
    """Load and flatten the distress corpus into (text, is_distress, note) tuples."""
    with open(CORPUS_PATH) as f:
        raw = yaml.safe_load(f)

    entries = []
    for _category, items in raw.items():
        if not isinstance(items, list):
            continue
        for item in items:
            entries.append(
                {
                    "text": item["text"],
                    "distress": item["distress"],
                    "note": item.get("note", ""),
                    "expected_domain": item.get("expected_domain"),
                }
            )
    return entries


ALL_ENTRIES = load_corpus()
DISTRESS_ENTRIES = [e for e in ALL_ENTRIES if e["distress"]]
NON_DISTRESS_ENTRIES = [e for e in ALL_ENTRIES if not e["distress"]]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_loader():
    """Isolate scenario loader state between tests."""
    reset_scenario_loader()
    yield
    reset_scenario_loader()


@pytest.fixture(scope="module")
def classifier():
    """Create a RiskClassifier using the real scenario files."""
    scenarios_path = Path(__file__).parent.parent.parent / "scenarios"
    loader = ScenarioLoader(str(scenarios_path))
    # LLM classifier disabled in tests - keyword + heuristic only
    return RiskClassifier(loader, use_llm=False)


# ---------------------------------------------------------------------------
# Individual parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", DISTRESS_ENTRIES, ids=[e["note"] for e in DISTRESS_ENTRIES])
def test_distress_detected(classifier, entry):
    """
    Each distress entry should produce either:
    - distress_present=True (multi-label signal from Phase 17.1), OR
    - domain in a sensitive/emotional category

    Keyword-only classifier (LLM disabled) uses domain as the primary signal.
    The domain must NOT be logistics for explicit distress content.
    """
    result = classifier.classify(entry["text"], [])

    domain = result["domain"]
    distress_present = result.get("distress_present", False)

    # Pass if multi-label distress signal fires OR domain is sensitive
    detected = distress_present or domain in DISTRESS_DOMAINS
    assert detected, (
        f"MISSED DISTRESS | domain={domain} | distress_present={distress_present} | "
        f"note={entry['note']} | text={entry['text'][:80]!r}"
    )


@pytest.mark.parametrize(
    "entry", NON_DISTRESS_ENTRIES, ids=[e["note"] for e in NON_DISTRESS_ENTRIES]
)
def test_no_false_positive(classifier, entry):
    """
    Benign entries should NOT trigger crisis domain.
    They may trigger emotional/relationships (some are mildly emotional),
    but should never produce domain=crisis or distress_present=True for
    obvious non-distress content.
    """
    result = classifier.classify(entry["text"], [])

    domain = result["domain"]
    distress_present = result.get("distress_present", False)

    # Hard failure: clearly benign content triggering crisis
    assert domain != "crisis", (
        f"FALSE POSITIVE (crisis) | domain={domain} | "
        f"note={entry['note']} | text={entry['text'][:80]!r}"
    )
    # Soft check: distress_present should not fire on obvious hyperbole/humour
    # (keyword-only classifier won't set distress_present, but future LLM-enabled runs will)
    if distress_present:
        pytest.xfail(
            f"distress_present=True on non-distress entry (acceptable if LLM-enabled): "
            f"{entry['note']}"
        )


@pytest.mark.parametrize(
    "entry",
    [e for e in DISTRESS_ENTRIES if e.get("expected_domain") == "crisis"],
    ids=[e["note"] for e in DISTRESS_ENTRIES if e.get("expected_domain") == "crisis"],
)
def test_crisis_entries_reach_crisis_domain(classifier, entry):
    """
    Entries explicitly marked expected_domain=crisis must produce domain=crisis.
    These are the highest-stakes entries - no compromise on these.
    """
    result = classifier.classify(entry["text"], [])
    assert result["domain"] == "crisis", (
        f"MISSED CRISIS | domain={result['domain']} | "
        f"note={entry['note']} | text={entry['text'][:80]!r}"
    )


# ---------------------------------------------------------------------------
# Aggregate rate tests (CI gates)
# ---------------------------------------------------------------------------


class TestDistressRates:
    """
    Aggregate false negative / false positive rate gates.
    These are the CI-blocking tests for Phase 17.3.
    """

    def test_false_negative_rate_below_threshold(self, classifier):
        """
        False negative rate on distress corpus must not exceed 5%.
        (Missing 2+ out of 36 distress entries fails the build.)
        """
        missed = []
        for entry in DISTRESS_ENTRIES:
            result = classifier.classify(entry["text"], [])
            domain = result["domain"]
            distress_present = result.get("distress_present", False)
            detected = distress_present or domain in DISTRESS_DOMAINS
            if not detected:
                missed.append(entry["note"])

        fn_rate = len(missed) / len(DISTRESS_ENTRIES)
        assert fn_rate <= 0.05, (
            f"False negative rate {fn_rate:.0%} exceeds 5% threshold. "
            f"Missed {len(missed)}/{len(DISTRESS_ENTRIES)} distress entries: {missed}"
        )

    def test_false_positive_rate_below_threshold(self, classifier):
        """
        False positive rate on non-distress corpus must not exceed 20%.
        (Misclassifying 5+ out of 24 benign entries as crisis fails the build.)
        Crisis domain is the only hard failure - emotional/relationships is acceptable.
        """
        crisis_false_positives = []
        for entry in NON_DISTRESS_ENTRIES:
            result = classifier.classify(entry["text"], [])
            if result["domain"] == "crisis":
                crisis_false_positives.append(entry["note"])

        fp_rate = len(crisis_false_positives) / len(NON_DISTRESS_ENTRIES)
        assert fp_rate <= 0.20, (
            f"False positive rate {fp_rate:.0%} exceeds 20% threshold. "
            f"Crisis false alarms on {len(crisis_false_positives)}/{len(NON_DISTRESS_ENTRIES)} "
            f"benign entries: {crisis_false_positives}"
        )

    def test_corpus_has_sufficient_coverage(self):
        """Corpus should have at least 30 distress and 20 non-distress entries."""
        assert (
            len(DISTRESS_ENTRIES) >= 30
        ), f"Distress corpus too small: {len(DISTRESS_ENTRIES)} entries (need 30+)"
        assert (
            len(NON_DISTRESS_ENTRIES) >= 20
        ), f"Non-distress corpus too small: {len(NON_DISTRESS_ENTRIES)} entries (need 20+)"

    def test_crisis_entries_present(self):
        """Corpus must include explicit crisis entries (highest risk category)."""
        crisis_entries = [e for e in DISTRESS_ENTRIES if e.get("expected_domain") == "crisis"]
        assert (
            len(crisis_entries) >= 5
        ), f"Not enough explicit crisis entries: {len(crisis_entries)} (need 5+)"
