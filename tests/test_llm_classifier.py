"""
Tests for LLM-Based Intelligent Classification (Phase 9)

Tests the LLMClassifier and its integration with RiskClassifier.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.llm_classifier import LLMClassifier, LRUCache, get_llm_classifier


class TestLRUCache:
    """Tests for the LRU cache implementation"""

    def test_cache_set_and_get(self):
        cache = LRUCache(max_size=3)
        cache.set("key1", {"domain": "logistics"})
        assert cache.get("key1") == {"domain": "logistics"}

    def test_cache_miss_returns_none(self):
        cache = LRUCache(max_size=3)
        assert cache.get("nonexistent") is None

    def test_cache_eviction_when_full(self):
        cache = LRUCache(max_size=2)
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})  # Should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") == {"value": 2}
        assert cache.get("key3") == {"value": 3}

    def test_cache_updates_lru_order(self):
        cache = LRUCache(max_size=2)
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.get("key1")  # Access key1, making key2 the oldest
        cache.set("key3", {"value": 3})  # Should evict key2
        assert cache.get("key1") == {"value": 1}
        assert cache.get("key2") is None
        assert cache.get("key3") == {"value": 3}

    def test_cache_clear(self):
        cache = LRUCache(max_size=3)
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestLLMClassifierConfig:
    """Tests for LLM classifier configuration loading"""

    def test_config_loads_from_yaml(self):
        classifier = LLMClassifier()
        assert "enabled" in classifier.config
        assert "prompt_template" in classifier.config
        assert "examples" in classifier.config

    def test_fast_path_patterns_loaded(self):
        classifier = LLMClassifier()
        assert len(classifier._fast_path_crisis) > 0
        assert len(classifier._fast_path_harmful) > 0
        assert "kill myself" in classifier._fast_path_crisis
        assert "kill someone" in classifier._fast_path_harmful

    def test_config_reload(self):
        classifier = LLMClassifier()
        original_enabled = classifier.config.get("enabled")
        classifier.reload_config()
        assert classifier.config.get("enabled") == original_enabled


class TestFastPathClassification:
    """Tests for safety-critical fast-path classification"""

    def test_crisis_fast_path(self):
        classifier = LLMClassifier()
        result = classifier._check_fast_path("I want to kill myself")
        assert result is not None
        assert result["domain"] == "crisis"
        assert result["emotional_intensity"] == 10.0
        assert result["is_personal_distress"] is True
        assert result["classification_method"] == "fast_path_crisis"

    def test_harmful_fast_path(self):
        classifier = LLMClassifier()
        result = classifier._check_fast_path("I want to kill someone")
        assert result is not None
        assert result["domain"] == "harmful"
        assert result["classification_method"] == "fast_path_harmful"

    def test_no_fast_path_for_normal_text(self):
        classifier = LLMClassifier()
        result = classifier._check_fast_path("Help me write an email")
        assert result is None

    def test_fast_path_case_insensitive(self):
        classifier = LLMClassifier()
        result = classifier._check_fast_path("I WANT TO KILL MYSELF")
        assert result is not None
        assert result["domain"] == "crisis"


class TestResponseParsing:
    """Tests for LLM response parsing"""

    def test_parse_valid_json(self):
        classifier = LLMClassifier()
        response = '{"domain": "logistics", "emotional_intensity": 2, "is_personal_distress": false, "confidence": 0.9}'
        result = classifier._parse_response(response)
        assert result is not None
        assert result["domain"] == "logistics"
        assert result["emotional_intensity"] == 2

    def test_parse_json_with_extra_text(self):
        classifier = LLMClassifier()
        response = 'Here is the classification:\n{"domain": "emotional", "emotional_intensity": 8, "is_personal_distress": true, "confidence": 0.85}\nDone.'
        result = classifier._parse_response(response)
        assert result is not None
        assert result["domain"] == "emotional"

    def test_parse_invalid_json(self):
        classifier = LLMClassifier()
        response = "This is not valid JSON at all"
        result = classifier._parse_response(response)
        assert result is None


class TestClassificationValidation:
    """Tests for classification result validation"""

    def test_validate_valid_result(self):
        classifier = LLMClassifier()
        result = {
            "domain": "logistics",
            "emotional_intensity": 3,
            "is_personal_distress": False,
            "confidence": 0.85,
        }
        validated = classifier._validate_classification(result)
        assert validated is not None
        assert validated["domain"] == "logistics"
        assert validated["emotional_intensity"] == 3

    def test_validate_normalizes_domain(self):
        classifier = LLMClassifier()
        result = {
            "domain": "practical",  # Should map to logistics
            "emotional_intensity": 2,
            "is_personal_distress": False,
            "confidence": 0.8,
        }
        validated = classifier._validate_classification(result)
        assert validated["domain"] == "logistics"

    def test_validate_clamps_intensity(self):
        classifier = LLMClassifier()
        result = {
            "domain": "logistics",
            "emotional_intensity": 15,  # Should be clamped to 10
            "is_personal_distress": False,
            "confidence": 0.8,
        }
        validated = classifier._validate_classification(result)
        assert validated["emotional_intensity"] == 10

    def test_validate_missing_domain_returns_none(self):
        classifier = LLMClassifier()
        result = {"emotional_intensity": 3, "is_personal_distress": False}
        validated = classifier._validate_classification(result)
        assert validated is None

    def test_validate_handles_string_booleans(self):
        classifier = LLMClassifier()
        result = {
            "domain": "emotional",
            "emotional_intensity": 8,
            "is_personal_distress": "true",  # String instead of bool
            "confidence": 0.9,
        }
        validated = classifier._validate_classification(result)
        assert validated["is_personal_distress"] is True


class TestCaching:
    """Tests for classification caching"""

    def test_cache_key_generation(self):
        classifier = LLMClassifier()
        key1 = classifier._get_cache_key("Hello world", "")
        key2 = classifier._get_cache_key("Hello world", "")
        key3 = classifier._get_cache_key("Different message", "")
        assert key1 == key2
        assert key1 != key3

    def test_cache_includes_context(self):
        classifier = LLMClassifier()
        key1 = classifier._get_cache_key("Hello", "context1")
        key2 = classifier._get_cache_key("Hello", "context2")
        assert key1 != key2


class TestPromptBuilding:
    """Tests for classification prompt construction"""

    def test_prompt_includes_message(self):
        classifier = LLMClassifier()
        prompt = classifier._build_prompt("Test message", "")
        assert "Test message" in prompt

    def test_prompt_wraps_message_in_xml_boundary(self):
        classifier = LLMClassifier()
        prompt = classifier._build_prompt("Test message", "")
        assert "<user_message>" in prompt
        assert "</user_message>" in prompt
        # Message content must still be present inside the boundary
        assert "Test message" in prompt

    def test_prompt_includes_domains(self):
        classifier = LLMClassifier()
        prompt = classifier._build_prompt("Test", "")
        assert "logistics" in prompt
        assert "emotional" in prompt
        assert "crisis" in prompt


class TestIntegration:
    """Integration tests with RiskClassifier"""

    def test_risk_classifier_with_llm_disabled(self):
        """Test that RiskClassifier works with LLM disabled"""
        from models.risk_classifier import RiskClassifier

        classifier = RiskClassifier(use_llm=False)
        result = classifier.classify("Help me write an email", [])
        assert "domain" in result
        assert result["classification_method"] == "keyword"

    def test_risk_classifier_classification_method_field(self):
        """Test that classification_method field is present"""
        from models.risk_classifier import RiskClassifier

        classifier = RiskClassifier(use_llm=False)
        result = classifier.classify("I feel sad today", [])
        assert "classification_method" in result

    def test_risk_classifier_llm_toggle(self):
        """Test enabling/disabling LLM classification at runtime"""
        from models.risk_classifier import RiskClassifier

        classifier = RiskClassifier(use_llm=False)
        assert classifier.is_llm_classification_enabled() is False
        # Note: This test would need Ollama running to fully test enabling


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_empty_message(self):
        classifier = LLMClassifier()
        result = classifier.classify("", [])
        assert result is None

    def test_whitespace_only_message(self):
        classifier = LLMClassifier()
        result = classifier.classify("   ", [])
        assert result is None

    def test_disabled_classifier_returns_none(self):
        classifier = LLMClassifier()
        classifier.config["enabled"] = False
        result = classifier.classify("Test message", [])
        assert result is None


class TestErrorInjection:
    """Tests for Ollama error scenarios — classifier should fail gracefully."""

    def test_connection_refused(self):
        """Connection refused should return None, not crash."""
        import httpx

        classifier = LLMClassifier()
        mock_client = Mock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        with patch("utils.http_client.get_http_client", return_value=mock_client):
            result = classifier._call_ollama("test prompt")
        assert result is None

    def test_timeout(self):
        """Timeout should return None, not crash."""
        import httpx

        classifier = LLMClassifier()
        mock_client = Mock()
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
        with patch("utils.http_client.get_http_client", return_value=mock_client):
            result = classifier._call_ollama("test prompt")
        assert result is None

    def test_malformed_json_response(self):
        """Non-JSON response should not crash classify()."""
        classifier = LLMClassifier()
        with patch.object(classifier, "_call_ollama", return_value="not valid json at all"):
            result = classifier.classify("How do I budget my money?", [])
        # Should return None since JSON parsing fails
        assert result is None

    def test_empty_response(self):
        """Empty response from Ollama should return None."""
        classifier = LLMClassifier()
        with patch.object(classifier, "_call_ollama", return_value=""):
            result = classifier.classify("Tell me about investing", [])
        assert result is None

    def test_http_500_error(self):
        """HTTP 500 from Ollama should return None."""
        import httpx

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=Mock(), response=Mock()
        )
        classifier = LLMClassifier()
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        with patch("utils.http_client.get_http_client", return_value=mock_client):
            result = classifier._call_ollama("test prompt")
        assert result is None


class TestTimingInstrumentation:
    """Tests for response time logging on LLMClassifier."""

    def test_last_call_duration_default_is_zero(self):
        classifier = LLMClassifier()
        assert classifier.last_call_duration == 0.0

    def test_last_call_duration_set_after_successful_call(self):
        classifier = LLMClassifier()
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"response": '{"domain": "logistics"}'}
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        with patch("utils.http_client.get_http_client", return_value=mock_client):
            classifier._call_ollama("test prompt")
        assert classifier.last_call_duration > 0.0

    def test_last_call_duration_not_set_on_timeout(self):
        """Timeout before response should leave last_call_duration at 0."""
        import httpx

        classifier = LLMClassifier()
        mock_client = Mock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        with patch("utils.http_client.get_http_client", return_value=mock_client):
            classifier._call_ollama("test prompt")
        assert classifier.last_call_duration == 0.0

    def test_call_duration_logged_at_info(self):
        classifier = LLMClassifier()
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"response": '{"domain": "logistics"}'}
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        import logging

        with patch("utils.http_client.get_http_client", return_value=mock_client):
            with patch.object(logging.getLogger("models.llm_classifier"), "info") as mock_log:
                classifier._call_ollama("test prompt")
        logged_messages = [str(call) for call in mock_log.call_args_list]
        assert any("llm_classifier.call" in msg for msg in logged_messages)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
