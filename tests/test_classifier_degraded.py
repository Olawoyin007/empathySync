"""
`classifier_degraded` fires only when the LLM was asked and gave nothing.

THREAT_MODEL.md records this as a reliability gap: with Ollama unreachable or the
classifier timing out, routing falls back to keyword matching, crisis and harmful
phrases still land, but the oblique cases only the LLM catches do not - and
nothing told the user the weaker path was in use.

`classification_method == "keyword"` cannot carry that message, because it is
also how three perfectly healthy situations read: a fast-path crisis or harmful
hit that bypasses the LLM on purpose, a short continuation skipped to save a
round-trip, and a classifier switched off by configuration. Warning on all four
would put a technical fault banner on screen during a crisis hard stop, which is
the worst moment available.

So these tests pin the distinction in both directions. The false-positive cases
matter more than the true one.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.risk_classifier import RiskClassifier  # noqa: E402


def _classifier(llm_behaviour=None, use_llm=True):
    """
    A RiskClassifier whose LLM layer behaves as asked.

    llm_behaviour: a return value for classify(), or an Exception to raise.
    """
    rc = RiskClassifier(use_llm=use_llm)
    llm = Mock()
    llm._check_fast_path = Mock(return_value=None)
    if isinstance(llm_behaviour, Exception):
        llm.classify = Mock(side_effect=llm_behaviour)
    else:
        llm.classify = Mock(return_value=llm_behaviour)
    rc._llm_classifier = llm
    return rc


class TestDegradedIsReported:
    """The one case that is a fault."""

    def test_an_unreachable_classifier_is_reported(self):
        import httpx

        rc = _classifier(httpx.ConnectError("Connection refused"))
        result = rc.classify("I have been feeling off lately", [])
        assert result.get("classifier_degraded") is True
        assert result["classification_method"] == "keyword"

    def test_a_classifier_returning_nothing_is_reported(self):
        """A timeout or an unparseable reply surfaces as None, not an exception."""
        rc = _classifier(None)
        result = rc.classify("I have been feeling off lately", [])
        assert result.get("classifier_degraded") is True


class TestHealthyKeywordRoutingIsNotReported:
    """
    The three cases that are not faults. A regression here is worse than missing
    the warning entirely: it would fire during a crisis hard stop.
    """

    def test_a_fast_path_crisis_hit_is_not_degraded(self):
        """
        The strongest path in the pipeline routes on keywords by design, without
        calling the LLM at all. It must never be labelled a malfunction.
        """
        rc = RiskClassifier(use_llm=True)
        llm = Mock()
        llm._check_fast_path = Mock(
            return_value={
                "domain": "crisis",
                "emotional_intensity": 9.0,
                "classification_method": "keyword",
            }
        )
        llm.classify = Mock(side_effect=AssertionError("the LLM must not be called"))
        rc._llm_classifier = llm

        result = rc.classify("I want to kill myself", [])
        assert result["domain"] == "crisis"
        assert "classifier_degraded" not in result

    def test_a_disabled_classifier_is_not_degraded(self):
        """Off by configuration is a choice, not a failure."""
        rc = _classifier(None, use_llm=False)
        result = rc.classify("I have been feeling off lately", [])
        assert "classifier_degraded" not in result

    def test_a_skipped_short_continuation_is_not_degraded(self):
        """
        Short replies inside an established domain streak skip the round-trip on
        purpose. The LLM is never asked, so there is nothing to report.
        """
        rc = _classifier(None)
        with patch.object(rc, "_is_short_continuation", return_value=True):
            result = rc.classify("yes", [], primary_domain="emotional", domain_streak=3)
        rc._llm_classifier.classify.assert_not_called()
        assert "classifier_degraded" not in result

    def test_a_working_classifier_is_not_degraded(self):
        rc = _classifier(
            {
                "domain": "emotional",
                "emotional_intensity": 5.0,
                "classification_method": "llm",
            }
        )
        result = rc.classify("I have been feeling off lately", [])
        assert result["classification_method"] == "llm"
        assert "classifier_degraded" not in result


class TestTheFlagIsAbsentNotFalse:
    """
    Absent rather than False, so a caller reading it with .get() cannot be
    confused by a falsy-but-present value, and so the field never appears on a
    healthy turn where someone might persist it by accident.
    """

    def test_healthy_turns_omit_the_key_entirely(self):
        rc = _classifier(
            {"domain": "logistics", "emotional_intensity": 1.0, "classification_method": "llm"}
        )
        assert "classifier_degraded" not in rc.classify("help me write an email", [])
