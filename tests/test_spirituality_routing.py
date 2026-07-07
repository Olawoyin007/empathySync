"""
Phase 21.4 - spirituality domain-routing corrections (#137).

Religious framing (deity names, clergy, rulings like "haram" / "god's will") is
high-precision but low-volume, so it routinely ties with - and loses to - the
relational or emotional surface of the same sentence. Every other override in the
pipeline is one-directional (emotional->specific, logistics->emotional), so once
the LLM reaches a relational label the spirituality restraint is silently dropped.

These tests are deterministic: the keyword pieces use keyword-only detection, and
the LLM override is exercised with a mocked classifier, so they run in CI.
"""

import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.risk_classifier import RiskClassifier  # noqa: E402


@pytest.fixture
def rc():
    return RiskClassifier(use_llm=False)


class TestKeywordDetection:
    def test_haram_beats_relational_surface(self, rc):
        # "haram" (added) + "allah" outweigh "marriage".
        assert (
            rc._detect_domain(
                "Is it haram to walk away from my marriage? I fear displeasing Allah."
            )
            == "spirituality"
        )

    def test_clergy_plus_grief_ties_break_to_spirituality(self, rc):
        # "my rabbi" (spirituality) ties 1-1-1 with "my mother" and "i'm angry";
        # the Phase 21.4 tie-break resolves to spirituality.
        assert (
            rc._detect_domain(
                "My rabbi says to keep faith, but since my mother died I'm angry at God"
            )
            == "spirituality"
        )

    def test_gods_will_is_detected(self, rc):
        assert (
            rc._detect_domain("I don't know if this is God's will or if I'm making a mistake.")
            == "spirituality"
        )

    def test_baptised_is_detected(self, rc):
        assert (
            rc._detect_domain("My family wants me to get baptised but I don't believe.")
            == "spirituality"
        )


class TestCultSubstringFix:
    """`cult` as a bare substring wrongly matched difficult / culture / cultivate."""

    @pytest.mark.parametrize(
        "text",
        [
            "How do I have a difficult conversation with someone I care about?",
            "Our company culture is toxic and I want to leave.",
            "I need to cultivate better habits this year.",
        ],
    )
    def test_cult_substring_no_longer_false_matches(self, rc, text):
        assert rc._detect_domain(text) != "spirituality"

    def test_genuine_cult_reference_still_detected(self, rc):
        assert (
            rc._detect_domain("I survived a cult leader who controlled everything")
            == "spirituality"
        )


class TestSpecificToSpiritualityOverride:
    """When the LLM picks a non-spirituality domain but keywords say spirituality."""

    def _classifier_with_llm(self, llm_domain):
        rc = RiskClassifier(use_llm=False)
        rc._use_llm = True
        fake = Mock()
        fake._check_fast_path = Mock(return_value=None)
        fake.classify = Mock(
            return_value={
                "domain": llm_domain,
                "emotional_intensity": 3.0,
                "distress_level": "none",
                "distress_present": False,
                "confidence": 0.95,  # high, so confidence-fallback paths are skipped
                "classification_method": "llm",
            }
        )
        rc._llm_classifier = fake
        return rc

    def test_relationships_label_corrected_to_spirituality(self):
        rc = self._classifier_with_llm("relationships")
        result = rc.classify(
            "Is it haram to walk away from my marriage? I fear displeasing Allah.", []
        )
        assert result["domain"] == "spirituality"
        assert result["spirituality_override"] is True

    def test_non_spiritual_input_is_left_alone(self):
        # No spirituality keyword -> override must not fire.
        rc = self._classifier_with_llm("relationships")
        result = rc.classify("My partner and I keep arguing about chores.", [])
        assert result["domain"] == "relationships"
        assert "spirituality_override" not in result

    def test_crisis_label_is_never_overridden(self):
        # Safety domains must win; the override must not pull crisis down to spirituality.
        rc = self._classifier_with_llm("crisis")
        result = rc.classify("I feel God has abandoned me and I want to die.", [])
        assert result["domain"] == "crisis"
