"""
Tests for src/utils/transcript.py

Covers generate_markdown_transcript() output format, edge cases,
and metadata rendering. Pure function tests - no mocking needed.
"""

from datetime import datetime

import pytest

from utils.transcript import generate_markdown_transcript


FIXED_DT = datetime(2026, 4, 1, 14, 30, 0)

SAMPLE_MESSAGES = [
    {"role": "user", "content": "Can you help me write a resignation email?"},
    {"role": "assistant", "content": "Of course. Here's a draft:\n\nDear Manager..."},
    {"role": "user", "content": "Thanks, that's great."},
    {"role": "assistant", "content": "Good luck with the transition."},
]


class TestMarkdownTranscriptFormat:
    """Output structure and content."""

    def test_contains_header(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT)
        assert "# empathySync - Conversation Transcript" in result

    def test_contains_export_date(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT)
        assert "2026-04-01" in result

    def test_user_messages_labelled_you(self):
        result = generate_markdown_transcript(SAMPLE_MESSAGES, exported_at=FIXED_DT)
        assert "**You**" in result

    def test_assistant_messages_labelled_empathysync(self):
        result = generate_markdown_transcript(SAMPLE_MESSAGES, exported_at=FIXED_DT)
        assert "**empathySync**" in result

    def test_message_content_present(self):
        result = generate_markdown_transcript(SAMPLE_MESSAGES, exported_at=FIXED_DT)
        assert "resignation email" in result
        assert "Dear Manager" in result

    def test_messages_separated_by_horizontal_rule(self):
        result = generate_markdown_transcript(SAMPLE_MESSAGES, exported_at=FIXED_DT)
        # Each message ends with ---
        assert result.count("---") >= len(SAMPLE_MESSAGES)

    def test_footer_contains_branding(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT)
        assert "local-first, private by design" in result


class TestMarkdownTranscriptMetadata:
    """Optional metadata fields in footer."""

    def test_session_turns_in_footer(self):
        result = generate_markdown_transcript(
            SAMPLE_MESSAGES, exported_at=FIXED_DT, session_turns=2
        )
        assert "2 turns" in result

    def test_domains_in_footer(self):
        result = generate_markdown_transcript(
            SAMPLE_MESSAGES,
            exported_at=FIXED_DT,
            domains=["logistics", "emotional"],
        )
        assert "logistics" in result
        assert "emotional" in result

    def test_app_version_in_footer(self):
        result = generate_markdown_transcript(
            SAMPLE_MESSAGES, exported_at=FIXED_DT, app_version="1.5.0"
        )
        assert "v1.5.0" in result

    def test_footer_without_optional_metadata(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT)
        # Should still have footer, just without turn/domain info
        assert "empathySync" in result.split("---")[-1]


class TestMarkdownTranscriptEdgeCases:
    """Edge cases and unusual inputs."""

    def test_empty_messages_returns_no_messages_note(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT)
        assert "No messages" in result

    def test_single_user_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = generate_markdown_transcript(msgs, exported_at=FIXED_DT)
        assert "Hello" in result
        assert "**You**" in result

    def test_unknown_role_skipped(self):
        msgs = [
            {"role": "system", "content": "Should not appear"},
            {"role": "user", "content": "Visible"},
        ]
        result = generate_markdown_transcript(msgs, exported_at=FIXED_DT)
        assert "Should not appear" not in result
        assert "Visible" in result

    def test_defaults_to_current_datetime_when_none(self):
        # Should not raise - just uses datetime.now()
        result = generate_markdown_transcript([])
        assert "# empathySync" in result

    def test_multiline_message_content_preserved(self):
        msgs = [{"role": "assistant", "content": "Line one\n\nLine two\n\nLine three"}]
        result = generate_markdown_transcript(msgs, exported_at=FIXED_DT)
        assert "Line one" in result
        assert "Line three" in result

    def test_empty_content_handled(self):
        msgs = [{"role": "user", "content": ""}]
        result = generate_markdown_transcript(msgs, exported_at=FIXED_DT)
        # Should not raise, label still present
        assert "**You**" in result

    def test_returns_string(self):
        result = generate_markdown_transcript(SAMPLE_MESSAGES, exported_at=FIXED_DT)
        assert isinstance(result, str)

    def test_empty_domains_list_no_topics_in_footer(self):
        result = generate_markdown_transcript([], exported_at=FIXED_DT, domains=[])
        assert "topics:" not in result
