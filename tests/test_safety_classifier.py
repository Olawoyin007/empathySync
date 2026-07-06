"""
Tests for the additive LlamaGuard safety classifier (Phase 21.2).

All tests run offline - the guard's HTTP call is mocked - so the suite needs no
Ollama. Covers response parsing, category-to-action mapping (including the
critical S6 -> RESTRAIN anti-regression rule and multi-category precedence), and
the classifier's disabled / fail-open behavior.
"""

import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.safety_classifier import (  # noqa: E402
    GuardVerdict,
    SafetyAction,
    SafetyClassifier,
    action_for_categories,
    parse_guard_response,
)


class TestParseGuardResponse:
    def test_safe(self):
        v = parse_guard_response("safe")
        assert v.safe is True
        assert v.categories == frozenset()

    def test_safe_case_and_whitespace_insensitive(self):
        assert parse_guard_response("  Safe\n").safe is True

    def test_unsafe_single_category(self):
        v = parse_guard_response("unsafe\nS6")
        assert v.safe is False
        assert v.categories == frozenset({"S6"})

    def test_unsafe_multi_category_comma(self):
        v = parse_guard_response("unsafe\nS1,S10")
        assert v.categories == frozenset({"S1", "S10"})

    def test_unsafe_multi_category_newlines(self):
        v = parse_guard_response("unsafe\nS1\nS9")
        assert v.categories == frozenset({"S1", "S9"})

    def test_unsafe_lowercase_codes_normalized(self):
        assert parse_guard_response("unsafe\ns6").categories == frozenset({"S6"})

    def test_empty_and_garbage_are_safe(self):
        assert parse_guard_response("").safe is True
        assert parse_guard_response(None).safe is True
        assert parse_guard_response("I think that's fine").safe is True

    def test_unsafe_without_codes_is_unsafe_but_empty(self):
        v = parse_guard_response("unsafe")
        assert v.safe is False
        assert v.categories == frozenset()


class TestActionMapping:
    def test_s6_specialized_advice_is_restrain_not_refuse(self):
        # The Phase 21.1 anti-regression rule: health/money questions must not be refused.
        assert action_for_categories({"S6"}) == SafetyAction.RESTRAIN

    def test_s11_self_harm_is_crisis(self):
        assert action_for_categories({"S11"}) == SafetyAction.CRISIS

    @pytest.mark.parametrize("cat", ["S1", "S2", "S3", "S4", "S5", "S7", "S9", "S10", "S12"])
    def test_dangerous_categories_refuse(self, cat):
        assert action_for_categories({cat}) == SafetyAction.REFUSE

    @pytest.mark.parametrize("cat", ["S8", "S13", "S14"])
    def test_out_of_scope_categories_allow(self, cat):
        assert action_for_categories({cat}) == SafetyAction.ALLOW

    def test_unknown_category_defaults_to_refuse(self):
        assert action_for_categories({"S99"}) == SafetyAction.REFUSE

    def test_empty_categories_allow(self):
        assert action_for_categories(set()) == SafetyAction.ALLOW

    def test_precedence_crisis_over_refuse(self):
        assert action_for_categories({"S1", "S11"}) == SafetyAction.CRISIS

    def test_precedence_refuse_over_restrain(self):
        assert action_for_categories({"S1", "S6"}) == SafetyAction.REFUSE

    def test_precedence_restrain_over_allow(self):
        assert action_for_categories({"S6", "S8"}) == SafetyAction.RESTRAIN


class TestGuardVerdictAction:
    def test_safe_verdict_allows(self):
        assert GuardVerdict(safe=True, categories=frozenset()).action == SafetyAction.ALLOW

    def test_unsafe_verdict_maps_categories(self):
        assert (
            GuardVerdict(safe=False, categories=frozenset({"S6"})).action == SafetyAction.RESTRAIN
        )


def _mock_client(content=None, raises=None):
    """An httpx-like client whose post() returns a guard response, or raises."""
    client = Mock()
    if raises is not None:
        client.post.side_effect = raises
        return client
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"message": {"content": content}})
    client.post = Mock(return_value=response)
    return client


class TestSafetyClassifier:
    def test_disabled_when_no_model_returns_allow_without_http(self):
        client = _mock_client(content="unsafe\nS1")
        clf = SafetyClassifier(model="", http_client=client)
        assert clf.enabled is False
        assert clf.classify("anything") == SafetyAction.ALLOW
        client.post.assert_not_called()

    def test_enabled_s6_maps_to_restrain(self):
        client = _mock_client(content="unsafe\nS6")
        clf = SafetyClassifier(model="llama-guard3:1b", http_client=client)
        assert clf.enabled is True
        assert clf.classify("is 800mg of ibuprofen too much?") == SafetyAction.RESTRAIN

    def test_enabled_safe_response_allows(self):
        clf = SafetyClassifier(model="llama-guard3:1b", http_client=_mock_client(content="safe"))
        assert clf.classify("how do I write a cover letter?") == SafetyAction.ALLOW

    def test_fail_open_on_http_error(self):
        client = _mock_client(raises=RuntimeError("connection refused"))
        clf = SafetyClassifier(model="llama-guard3:1b", http_client=client)
        assert clf.classify("anything") == SafetyAction.ALLOW

    def test_calls_chat_endpoint_with_model(self):
        client = _mock_client(content="safe")
        clf = SafetyClassifier(model="llama-guard3:1b", http_client=client)
        clf.classify("hello")
        args, kwargs = client.post.call_args
        assert args[0].endswith("/api/chat")
        assert kwargs["json"]["model"] == "llama-guard3:1b"
        assert kwargs["json"]["messages"][0]["content"] == "hello"
