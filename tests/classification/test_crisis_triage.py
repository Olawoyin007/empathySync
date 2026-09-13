"""
Crisis Triage Test Suite

Parametrized tests running the crisis triage corpus through
RiskClassifier.classify() with the LLM disabled.

Primary metric: FALSE NEGATIVE RATE on oblique ideation - must be 0%.
  Missing the crisis hard-stop is the dangerous failure mode: the message still
  gets warm emotional support, so nothing looks broken, but the hotline never
  appears.

Secondary metric: FALSE POSITIVE RATE on intense-but-not-suicidal messages -
  must be 0%. An unearned hotline redirect on grief or money stress teaches
  people that the floor is noise.

Keyword-only by design. This is the deterministic floor that has to hold when
the LLM is wrong, disabled, or Ollama is down - see the safety keyword override
in risk_classifier.classify(), where a crisis keyword match overrules the LLM.
"""

import sys
from pathlib import Path

import pytest
import yaml

# Add src to path so imports work the same as the main test suite
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.risk_classifier import RiskClassifier
from utils.scenario_loader import ScenarioLoader, reset_scenario_loader

CORPUS_PATH = Path(__file__).parent / "crisis_triage_corpus.yaml"


def load_corpus(key):
    """Load one section of the triage corpus as a list of entries."""
    with open(CORPUS_PATH) as f:
        raw = yaml.safe_load(f)
    return raw.get(key, [])


IDEATION_ENTRIES = load_corpus("oblique_ideation")
BENIGN_ENTRIES = load_corpus("intense_benign")
ACCEPTED_FP_ENTRIES = load_corpus("accepted_fp")


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
    return RiskClassifier(loader, use_llm=False)


@pytest.mark.parametrize("entry", IDEATION_ENTRIES, ids=[e["note"] for e in IDEATION_ENTRIES])
def test_oblique_ideation_reaches_crisis(classifier, entry):
    """Oblique ideation must reach the crisis hard-stop, not emotional support."""
    result = classifier.classify(entry["text"], [])
    assert result["domain"] == "crisis", (
        f"UNDER-TRIAGED | domain={result['domain']} | "
        f"note={entry['note']} | text={entry['text']!r}"
    )


@pytest.mark.parametrize("entry", BENIGN_ENTRIES, ids=[e["note"] for e in BENIGN_ENTRIES])
def test_intense_benign_stays_off_the_hard_stop(classifier, entry):
    """Intense but non-suicidal messages must not trigger the crisis hard-stop."""
    result = classifier.classify(entry["text"], [])
    assert (
        result["domain"] != "crisis"
    ), f"FALSE ESCALATION | note={entry['note']} | text={entry['text']!r}"


def test_apostrophe_variants_do_not_drop_the_floor():
    """
    A curly apostrophe (U+2019 - what phone keyboards emit) must not drop a
    message off the crisis floor. 19 crisis triggers contain an apostrophe.
    """
    scenarios_path = Path(__file__).parent.parent.parent / "scenarios"
    rc = RiskClassifier(ScenarioLoader(str(scenarios_path)), use_llm=False)
    straight = "I can't do this anymore"
    curly = "I can’t do this anymore"
    assert rc.classify(straight, [])["domain"] == "crisis"
    assert (
        rc.classify(curly, [])["domain"] == "crisis"
    ), "curly apostrophe dropped the message off the crisis floor"


def test_accepted_false_positives_are_recorded(classifier):
    """
    The corpus records benign messages that escalate today rather than hiding
    them. Not asserted either way - this only reports, so a future matcher
    improvement shrinks the list instead of breaking the build.
    """
    still_escalating = [
        e["text"]
        for e in ACCEPTED_FP_ENTRIES
        if classifier.classify(e["text"], [])["domain"] == "crisis"
    ]
    print(f"\naccepted false positives still escalating: {len(still_escalating)}")
    for text in still_escalating:
        print(f"  {text!r}")
