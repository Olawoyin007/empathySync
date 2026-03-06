"""
Tests for src/interfaces/cli_adapter.py

Covers:
- CLIAdapter initialization
- render_result() display logic (response, risk, policy, cooldown, interactions)
- render_stream() streaming display and finalization
- prompt_intent_shift() user interaction
- prompt_graduation() user interaction
- run() main loop with quit/exit/summary commands
- Error handling (EOFError, KeyboardInterrupt)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.conversation_result import ConversationResult
from interfaces.cli_adapter import CLIAdapter


def make_session():
    """Create a mock ConversationSession with required attributes."""
    session = MagicMock()
    session.acknowledged_shift = False
    session.finalize_stream.return_value = ConversationResult(response="final response")
    session.get_session_summary.return_value = {
        "turn_count": 5,
        "domains_touched": ["logistics", "health"],
        "max_risk_weight": 3.5,
    }
    return session


def make_adapter(session=None):
    """Create a CLIAdapter with a mock session."""
    if session is None:
        session = make_session()
    return CLIAdapter(session=session)


class TestCLIAdapterInit:
    """Tests for CLIAdapter initialization."""

    def test_stores_session(self):
        session = make_session()
        adapter = CLIAdapter(session=session)
        assert adapter.session is session

    def test_implements_interface_methods(self):
        adapter = make_adapter()
        assert hasattr(adapter, "render_result")
        assert hasattr(adapter, "render_stream")
        assert hasattr(adapter, "prompt_intent_shift")
        assert hasattr(adapter, "prompt_graduation")
        assert hasattr(adapter, "run")


class TestRenderResult:
    """Tests for render_result() display logic."""

    def test_prints_response(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(response="Hello there")
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Hello there" in captured.out

    def test_prints_risk_assessment(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="Some response",
            risk_assessment={
                "domain": "health",
                "risk_weight": 7.0,
                "classification_method": "llm",
            },
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "health" in captured.out
        assert "7.0" in captured.out
        assert "llm" in captured.out

    def test_prints_risk_assessment_defaults(self, capsys):
        """When risk_assessment has missing keys, defaults are used."""
        adapter = make_adapter()
        result = ConversationResult(
            response="response",
            risk_assessment={"domain": None},  # non-empty dict so truthy
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        # .get() defaults: domain->unknown (None is returned, not default),
        # risk_weight->0, classification_method->keyword
        assert "0.0" in captured.out
        assert "keyword" in captured.out

    def test_empty_risk_assessment_dict_prints_nothing(self, capsys):
        """Empty dict is falsy, so no risk info is printed."""
        adapter = make_adapter()
        result = ConversationResult(
            response="response",
            risk_assessment={},
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "unknown" not in captured.out

    def test_prints_policy_action(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="response",
            policy_action={"type": "crisis_stop"},
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Policy: crisis_stop" in captured.out

    def test_prints_policy_action_missing_type(self, capsys):
        """When policy_action has a key but type is missing, default empty string used."""
        adapter = make_adapter()
        result = ConversationResult(
            response="response",
            policy_action={"reason": "some reason"},  # non-empty dict, but no "type"
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Policy:" in captured.out

    def test_empty_policy_action_dict_prints_nothing(self, capsys):
        """Empty dict is falsy, so no policy info is printed."""
        adapter = make_adapter()
        result = ConversationResult(
            response="response",
            policy_action={},
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Policy" not in captured.out

    def test_cooldown_message(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="Too many sessions today",
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "[Cooldown]" in captured.out
        assert "Too many sessions today" in captured.out

    def test_cooldown_with_suggested_person(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="Take a break",
            suggested_handoff_person="Alice",
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Alice" in captured.out
        assert "reaching out" in captured.out.lower() or "Consider reaching out" in captured.out

    def test_cooldown_without_suggested_person(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="Take a break",
            suggested_handoff_person=None,
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "Take a break" in captured.out
        assert "reaching out" not in captured.out.lower()

    def test_cooldown_skips_response_and_risk(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="should not appear",
            is_cooldown_active=True,
            cooldown_message="cooldown active",
            risk_assessment={"domain": "health", "risk_weight": 7.0},
        )
        adapter.render_result(result)
        captured = capsys.readouterr()
        assert "should not appear" not in captured.out
        assert "health" not in captured.out

    def test_no_response_prints_nothing_for_response(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(response="")
        adapter.render_result(result)
        captured = capsys.readouterr()
        # Empty response should not produce meaningful output
        assert captured.out.strip() == ""

    @patch("builtins.input", return_value="1")
    def test_pending_shift_prompts_user_and_accepts(self, mock_input, capsys):
        session = make_session()
        session.acknowledged_shift = False
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="response",
            pending_shift={"to_intent": "emotional"},
        )
        adapter.render_result(result)
        session.acknowledge_intent_shift.assert_called_once_with(True)

    @patch("builtins.input", return_value="2")
    def test_pending_shift_prompts_user_and_declines(self, mock_input, capsys):
        session = make_session()
        session.acknowledged_shift = False
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="response",
            pending_shift={"to_intent": "emotional"},
        )
        adapter.render_result(result)
        session.acknowledge_intent_shift.assert_called_once_with(False)

    def test_pending_shift_skipped_when_acknowledged(self, capsys):
        session = make_session()
        session.acknowledged_shift = True
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="response",
            pending_shift={"to_intent": "emotional"},
        )
        adapter.render_result(result)
        session.acknowledge_intent_shift.assert_not_called()

    @patch("builtins.input", return_value="1")
    def test_pending_graduation_accept(self, mock_input, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="response",
            pending_graduation={"category": "email", "prompt": "You seem good at this!"},
        )
        adapter.render_result(result)
        session.accept_graduation.assert_called_once()
        session.dismiss_graduation.assert_not_called()

    @patch("builtins.input", return_value="2")
    def test_pending_graduation_dismiss(self, mock_input, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="response",
            pending_graduation={"category": "email", "prompt": "You seem good at this!"},
        )
        adapter.render_result(result)
        session.dismiss_graduation.assert_called_once()
        session.accept_graduation.assert_not_called()


class TestRenderStream:
    """Tests for render_stream() streaming display."""

    def test_streams_tokens_to_stdout(self, capsys):
        session = make_session()
        session.finalize_stream.return_value = ConversationResult(response="Hello world")
        adapter = CLIAdapter(session=session)

        tokens = iter(["Hello", " ", "world"])
        result = ConversationResult(response="", response_stream=tokens)

        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "Hello world" in captured.out

    def test_calls_finalize_stream(self, capsys):
        session = make_session()
        session.finalize_stream.return_value = ConversationResult(response="done")
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["token"]))
        adapter.render_stream(result)
        session.finalize_stream.assert_called_once()

    def test_shows_risk_from_finalized_result(self, capsys):
        session = make_session()
        session.finalize_stream.return_value = ConversationResult(
            response="done",
            risk_assessment={
                "domain": "money",
                "risk_weight": 6.0,
                "classification_method": "keyword",
            },
        )
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["token"]))
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "money" in captured.out
        assert "6.0" in captured.out

    def test_shows_policy_from_finalized_result(self, capsys):
        session = make_session()
        session.finalize_stream.return_value = ConversationResult(
            response="done",
            policy_action={"type": "turn_limit"},
        )
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["ok"]))
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "Policy: turn_limit" in captured.out

    def test_cooldown_in_stream(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="Please rest",
        )
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "[Cooldown]" in captured.out
        assert "Please rest" in captured.out

    def test_cooldown_with_handoff_person_in_stream(self, capsys):
        adapter = make_adapter()
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="Break time",
            suggested_handoff_person="Bob",
        )
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "Bob" in captured.out

    def test_cooldown_skips_streaming(self, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        result = ConversationResult(
            response="",
            is_cooldown_active=True,
            cooldown_message="cooldown",
            response_stream=iter(["should", "not", "appear"]),
        )
        adapter.render_stream(result)
        session.finalize_stream.assert_not_called()

    def test_non_streaming_fallback(self, capsys):
        """When no stream but response is set, prints response directly."""
        session = make_session()
        adapter = CLIAdapter(session=session)
        result = ConversationResult(response="fallback text")
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert "fallback text" in captured.out
        session.finalize_stream.assert_not_called()

    @patch("builtins.input", return_value="1")
    def test_stream_pending_shift_after_finalize(self, mock_input, capsys):
        session = make_session()
        session.acknowledged_shift = False
        final_result = ConversationResult(
            response="done",
            pending_shift={"to_intent": "emotional"},
        )
        session.finalize_stream.return_value = final_result
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["token"]))
        adapter.render_stream(result)
        session.acknowledge_intent_shift.assert_called_once_with(True)

    @patch("builtins.input", return_value="1")
    def test_stream_pending_graduation_after_finalize(self, mock_input, capsys):
        session = make_session()
        final_result = ConversationResult(
            response="done",
            pending_graduation={"category": "coding", "prompt": "Nice work!"},
        )
        session.finalize_stream.return_value = final_result
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["t"]))
        adapter.render_stream(result)
        session.accept_graduation.assert_called_once()


class TestPromptIntentShift:
    """Tests for prompt_intent_shift() user interaction."""

    @patch("builtins.input", return_value="1")
    def test_returns_true_for_choice_1(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({"to_intent": "emotional"})
        assert result is True

    @patch("builtins.input", return_value="2")
    def test_returns_false_for_choice_2(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({"to_intent": "emotional"})
        assert result is False

    @patch("builtins.input", return_value="anything else")
    def test_returns_false_for_invalid_input(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({})
        assert result is False

    @patch("builtins.input", side_effect=EOFError)
    def test_returns_false_on_eof(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({})
        assert result is False

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_returns_false_on_keyboard_interrupt(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({})
        assert result is False

    @patch("builtins.input", return_value="1")
    def test_displays_prompt_text(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.prompt_intent_shift({"to_intent": "emotional"})
        captured = capsys.readouterr()
        assert "more than just the task" in captured.out
        assert "1." in captured.out
        assert "2." in captured.out

    @patch("builtins.input", return_value=" 1 ")
    def test_strips_whitespace_from_input(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_intent_shift({})
        assert result is True


class TestPromptGraduation:
    """Tests for prompt_graduation() user interaction."""

    @patch("builtins.input", return_value="1")
    def test_returns_accept_for_choice_1(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_graduation("email", "You've written many emails!")
        assert result == "accept"

    @patch("builtins.input", return_value="2")
    def test_returns_dismiss_for_choice_2(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_graduation("email", "You've written many emails!")
        assert result == "dismiss"

    @patch("builtins.input", return_value="anything")
    def test_returns_dismiss_for_invalid_input(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_graduation("coding", "prompt text")
        assert result == "dismiss"

    @patch("builtins.input", side_effect=EOFError)
    def test_returns_dismiss_on_eof(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_graduation("coding", "prompt text")
        assert result == "dismiss"

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_returns_dismiss_on_keyboard_interrupt(self, mock_input, capsys):
        adapter = make_adapter()
        result = adapter.prompt_graduation("coding", "prompt text")
        assert result == "dismiss"

    @patch("builtins.input", return_value="1")
    def test_displays_prompt_text_and_options(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.prompt_graduation("email", "You've mastered email writing!")
        captured = capsys.readouterr()
        assert "You've mastered email writing!" in captured.out
        assert "Show me some tips" in captured.out
        assert "Just help me" in captured.out


class TestRun:
    """Tests for run() main conversation loop."""

    @patch("builtins.input", side_effect=["quit"])
    def test_quit_command(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=["exit"])
    def test_exit_command(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=["q"])
    def test_q_command(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=["EXIT"])
    def test_exit_case_insensitive(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=["Quit"])
    def test_quit_case_insensitive(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_exits_gracefully(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_exits_gracefully(self, mock_input, capsys):
        adapter = make_adapter()
        adapter.run()
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("builtins.input", side_effect=["", "quit"])
    def test_empty_input_is_ignored(self, mock_input, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        adapter.run()
        session.process_message_stream.assert_not_called()

    @patch("builtins.input", side_effect=["   ", "quit"])
    def test_whitespace_only_input_is_ignored(self, mock_input, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        adapter.run()
        session.process_message_stream.assert_not_called()

    @patch("builtins.input", side_effect=["summary", "quit"])
    def test_summary_command(self, mock_input, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        adapter.run()
        captured = capsys.readouterr()
        assert "Turns: 5" in captured.out
        assert "logistics" in captured.out
        assert "health" in captured.out
        assert "3.5" in captured.out
        session.get_session_summary.assert_called_once()

    @patch("builtins.input", side_effect=["summary", "quit"])
    def test_summary_with_empty_domains(self, mock_input, capsys):
        session = make_session()
        session.get_session_summary.return_value = {
            "turn_count": 0,
            "domains_touched": [],
            "max_risk_weight": 0,
        }
        adapter = CLIAdapter(session=session)
        adapter.run()
        captured = capsys.readouterr()
        assert "Turns: 0" in captured.out

    @patch("builtins.input", side_effect=["hello", "quit"])
    def test_processes_message_via_session(self, mock_input, capsys):
        session = make_session()
        streaming_result = ConversationResult(
            response="Hi there",
            response_stream=None,
        )
        session.process_message_stream.return_value = streaming_result
        adapter = CLIAdapter(session=session)
        adapter.run()
        session.process_message_stream.assert_called_once_with("hello")

    @patch("builtins.input", side_effect=["hello", "quit"])
    def test_streaming_result_calls_render_stream(self, mock_input, capsys):
        session = make_session()
        streaming_result = ConversationResult(
            response="",
            response_stream=iter(["Hi", " ", "there"]),
        )
        session.process_message_stream.return_value = streaming_result
        session.finalize_stream.return_value = ConversationResult(response="Hi there")
        adapter = CLIAdapter(session=session)
        adapter.run()
        captured = capsys.readouterr()
        assert "Hi there" in captured.out

    @patch("builtins.input", side_effect=["hello", "quit"])
    def test_non_streaming_result_calls_render_result(self, mock_input, capsys):
        session = make_session()
        result = ConversationResult(response="Non-streaming response")
        session.process_message_stream.return_value = result
        adapter = CLIAdapter(session=session)
        adapter.run()
        captured = capsys.readouterr()
        assert "Non-streaming response" in captured.out

    @patch("builtins.input", side_effect=["hello", "world", "quit"])
    def test_multiple_messages_before_quit(self, mock_input, capsys):
        session = make_session()
        session.process_message_stream.return_value = ConversationResult(response="reply")
        adapter = CLIAdapter(session=session)
        adapter.run()
        assert session.process_message_stream.call_count == 2
        session.process_message_stream.assert_any_call("hello")
        session.process_message_stream.assert_any_call("world")

    def test_run_prints_banner(self, capsys):
        with patch("builtins.input", side_effect=["quit"]):
            adapter = make_adapter()
            adapter.run()
        captured = capsys.readouterr()
        assert "empathySync" in captured.out
        assert "exit" in captured.out.lower() or "quit" in captured.out.lower()

    @patch("builtins.input", side_effect=["hello", "summary", "quit"])
    def test_summary_does_not_process_as_message(self, mock_input, capsys):
        session = make_session()
        session.process_message_stream.return_value = ConversationResult(response="r")
        adapter = CLIAdapter(session=session)
        adapter.run()
        # Only "hello" should be processed as a message, not "summary"
        session.process_message_stream.assert_called_once_with("hello")


class TestRenderStreamEdgeCases:
    """Edge cases for streaming display."""

    def test_empty_stream(self, capsys):
        session = make_session()
        session.finalize_stream.return_value = ConversationResult(response="")
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter([]))
        adapter.render_stream(result)
        session.finalize_stream.assert_called_once()

    def test_stream_shift_skipped_when_acknowledged(self, capsys):
        session = make_session()
        session.acknowledged_shift = True
        final_result = ConversationResult(
            response="done",
            pending_shift={"to_intent": "emotional"},
        )
        session.finalize_stream.return_value = final_result
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["t"]))
        adapter.render_stream(result)
        session.acknowledge_intent_shift.assert_not_called()

    @patch("builtins.input", return_value="2")
    def test_stream_graduation_dismiss(self, mock_input, capsys):
        session = make_session()
        final_result = ConversationResult(
            response="done",
            pending_graduation={"category": "coding", "prompt": "Great job!"},
        )
        session.finalize_stream.return_value = final_result
        adapter = CLIAdapter(session=session)

        result = ConversationResult(response="", response_stream=iter(["t"]))
        adapter.render_stream(result)
        session.dismiss_graduation.assert_called_once()
        session.accept_graduation.assert_not_called()

    def test_no_response_no_stream_prints_nothing(self, capsys):
        session = make_session()
        adapter = CLIAdapter(session=session)
        result = ConversationResult(response="")
        adapter.render_stream(result)
        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        session.finalize_stream.assert_not_called()
