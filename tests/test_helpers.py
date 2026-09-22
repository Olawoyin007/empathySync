"""
Tests for src/utils/helpers.py

Covers:
- setup_logging() configuration
- validate_environment() delegation
- format_wellness_tip() formatting
- create_progress_summary() edge cases
- build_handoff_link() OS handoff URLs (Phase 25.3)
"""

import logging
import pytest
from unittest.mock import patch, MagicMock


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_creates_log_directory(self, tmp_path):
        logs_dir = tmp_path / "logs"

        mock_settings = MagicMock()
        mock_settings.LOGS_DIR = logs_dir
        mock_settings.LOG_FILE = "test.log"
        mock_settings.LOG_LEVEL = "INFO"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "test"

        with patch("utils.helpers.settings", mock_settings):
            from utils.helpers import setup_logging

            setup_logging()

        assert logs_dir.exists()

    def test_sets_log_level_from_settings(self, tmp_path):
        logs_dir = tmp_path / "logs"

        mock_settings = MagicMock()
        mock_settings.LOGS_DIR = logs_dir
        mock_settings.LOG_FILE = "test.log"
        mock_settings.LOG_LEVEL = "DEBUG"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "test"

        with (
            patch("utils.helpers.settings", mock_settings),
            patch("logging.basicConfig") as mock_basic,
        ):
            from utils.helpers import setup_logging

            setup_logging()

        mock_basic.assert_called_once()
        call_kwargs = mock_basic.call_args
        assert call_kwargs[1]["level"] == logging.DEBUG


class TestValidateEnvironment:
    """Tests for validate_environment()."""

    def test_returns_empty_when_valid(self):
        mock_settings = MagicMock()
        mock_settings.validate_config.return_value = []

        with patch("utils.helpers.settings", mock_settings):
            from utils.helpers import validate_environment

            result = validate_environment()

        assert result == []

    def test_returns_missing_config(self):
        mock_settings = MagicMock()
        mock_settings.validate_config.return_value = ["OLLAMA_HOST", "OLLAMA_MODEL"]

        with patch("utils.helpers.settings", mock_settings):
            from utils.helpers import validate_environment

            result = validate_environment()

        assert "OLLAMA_HOST" in result
        assert "OLLAMA_MODEL" in result


class TestFormatWellnessTip:
    """Tests for format_wellness_tip()."""

    def test_includes_tip_text(self):
        from utils.helpers import format_wellness_tip

        result = format_wellness_tip("Stay hydrated")
        assert "Stay hydrated" in result

    def test_includes_wellness_insight_label(self):
        from utils.helpers import format_wellness_tip

        result = format_wellness_tip("Take breaks")
        assert "Wellness Insight" in result


class TestCreateProgressSummary:
    """Tests for create_progress_summary()."""

    def test_zero_conversations_returns_welcome(self):
        from utils.helpers import create_progress_summary

        result = create_progress_summary(0, 0)
        assert "Welcome" in result

    def test_single_day_says_today(self):
        from utils.helpers import create_progress_summary

        result = create_progress_summary(3, 1)
        assert "today" in result
        assert "3" in result

    def test_multiple_days_shows_average(self):
        from utils.helpers import create_progress_summary

        result = create_progress_summary(10, 5)
        assert "over 5 days" in result
        assert "2.0" in result

    def test_zero_days_no_division_error(self):
        from utils.helpers import create_progress_summary

        # Should not raise ZeroDivisionError
        result = create_progress_summary(5, 0)
        assert isinstance(result, str)
        assert "5" in result


class TestBuildHandoffLinks:
    """Phase 25.3 - a drafted reach-out should not have to be retyped.

    The links hand the draft to the user's own mail or messaging app. It is a
    handoff, not an integration: no SMTP, no API, nothing leaves the machine
    until the user presses send in their own client.
    """

    @pytest.mark.parametrize(
        "contact,expected_target",
        [
            ("sam@example.com", "mailto:sam@example.com"),
            ("Sam.Okafor+notes@sub.example.co.uk", "mailto:Sam.Okafor%2Bnotes@sub.example.co.uk"),
        ],
    )
    def test_email_contacts_become_mailto(self, contact, expected_target):
        from utils.helpers import build_handoff_links

        links = build_handoff_links(contact, "hello")
        assert len(links) == 1
        kind, url = links[0]
        assert kind == "email"
        assert url.startswith(expected_target + "?body=")

    @pytest.mark.parametrize(
        "contact,expected_number",
        [
            ("+44 7700 900123", "+447700900123"),
            ("(555) 123-4567", "5551234567"),
            ("07700900123", "07700900123"),
            ("555.123.4567", "5551234567"),
        ],
    )
    def test_phone_contacts_offer_sms_then_call(self, contact, expected_number):
        """Cosmetic characters are stripped; a leading + is kept, because
        dropping it turns an international number into a local one.

        sms: comes first because it carries the draft. tel: cannot, which is
        why it is second rather than instead.
        """
        from utils.helpers import build_handoff_links

        links = build_handoff_links(contact, "hello")
        assert [kind for kind, _ in links] == ["sms", "tel"]
        assert links[0][1].startswith(f"sms:{expected_number}?body=")
        assert links[1][1] == f"tel:{expected_number}"

    def test_call_link_carries_no_body(self):
        """A tel: URL has nowhere to put a message. Appending one would produce
        a link that silently fails to dial in some clients."""
        from utils.helpers import build_handoff_links

        links = build_handoff_links("+44 7700 900123", "please do not end up in the dial string")
        tel = dict(links)["tel"]
        assert "?" not in tel
        assert "body" not in tel

    @pytest.mark.parametrize(
        "contact",
        [
            "",
            "   ",
            "the pub on Thursdays",
            "ask her mum first",
            "@handle",
            "1234",  # too short to be a phone number
        ],
    )
    def test_unaddressable_contacts_return_nothing(self, contact):
        """A contact the OS cannot act on is not a bug - "the pub on Thursdays"
        is a perfectly good thing to have saved. It falls back to copy."""
        from utils.helpers import build_handoff_links

        assert build_handoff_links(contact, "hello") == []

    def test_none_contact_is_safe(self):
        from utils.helpers import build_handoff_links

        assert build_handoff_links(None, "hello") == []

    def test_message_is_percent_encoded(self):
        """An unencoded & or # truncates the body in the receiving client, so
        the draft would arrive cut in half."""
        from utils.helpers import build_handoff_links
        from urllib.parse import unquote

        message = "Hi Sam & Ada - can we talk? #worried\n\nIt's about the flat (50% mine)."
        url = build_handoff_links("sam@example.com", message)[0][1]

        body = url.split("?body=", 1)[1]
        assert "&" not in body
        assert "#" not in body
        assert unquote(body) == message

    def test_empty_message_still_produces_a_link(self):
        """The text area can be cleared. Opening an empty draft is still better
        than no route out of the app."""
        from utils.helpers import build_handoff_links

        links = build_handoff_links("sam@example.com", "")
        assert links == [("email", "mailto:sam@example.com?body=")]
