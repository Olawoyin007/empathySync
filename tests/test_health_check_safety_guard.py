"""
Tests for the safety-guard startup health check (Phase 21.2 follow-up).

Offline - the Ollama /api/tags call is mocked. Verifies that a configured but
unpulled guard model is surfaced as a warning (the gap this check closes), while
a disabled or present guard reports cleanly. The check is always non-critical:
the guard fails open, so it must never block startup.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config.settings import settings  # noqa: E402
from utils.health_check import check_safety_guard  # noqa: E402


def _client_with_models(names):
    client = Mock()
    response = Mock()
    response.status_code = 200
    response.json = Mock(return_value={"models": [{"name": n} for n in names]})
    client.get = Mock(return_value=response)
    return client


@pytest.fixture
def guard_model(monkeypatch):
    """Set OLLAMA_SAFETY_MODEL for the duration of a test, restored after."""

    def _set(value):
        monkeypatch.setattr(settings, "OLLAMA_SAFETY_MODEL", value)

    return _set


class TestCheckSafetyGuard:
    def test_disabled_when_unset(self, guard_model):
        guard_model("")
        status = check_safety_guard()
        assert status.ok is True
        assert status.critical is False
        assert "Disabled" in status.message

    def test_available_when_pulled(self, guard_model):
        guard_model("llama-guard3:1b")
        client = _client_with_models(["gemma3:12b", "llama-guard3:1b"])
        with patch("utils.health_check.get_http_client", return_value=client):
            status = check_safety_guard()
        assert status.ok is True
        assert "available" in status.message

    def test_configured_but_missing_warns(self, guard_model):
        guard_model("llama-guard3:1b")
        client = _client_with_models(["gemma3:12b"])  # guard not pulled
        with patch("utils.health_check.get_http_client", return_value=client):
            status = check_safety_guard()
        # Non-critical (fails open), but surfaces the misconfiguration.
        assert status.ok is True
        assert status.critical is False
        assert "not found" in status.message
        assert "ollama pull llama-guard3:1b" in status.details

    def test_matches_tagged_variant(self, guard_model):
        # Configured without a tag should still match a tagged model name.
        guard_model("llama-guard3")
        client = _client_with_models(["llama-guard3:1b"])
        with patch("utils.health_check.get_http_client", return_value=client):
            status = check_safety_guard()
        assert "available" in status.message

    def test_fails_open_on_http_error(self, guard_model):
        guard_model("llama-guard3:1b")
        client = Mock()
        client.get = Mock(side_effect=RuntimeError("connection refused"))
        with patch("utils.health_check.get_http_client", return_value=client):
            status = check_safety_guard()
        assert status.ok is True
        assert status.critical is False
        assert "Cannot verify" in status.message
