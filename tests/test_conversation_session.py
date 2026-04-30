"""
Tests for src/models/conversation_session.py

Covers:
- ConversationSession initialization and default state
- process_message() full pipeline with mocked dependencies
- process_message_stream() + finalize_stream() streaming pipeline
- Cooldown enforcement
- Connection-seeking first-turn handling
- Intent detection and shift detection
- Graduation checking
- Handoff suggestions from trusted network
- acknowledge_intent_shift() and dismiss/accept graduation
- reset() clears all state
- turn_count property
- Message history management
- get_session_summary() delegation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.conversation_session import ConversationSession, ConnectionSteering
from models.conversation_result import ConversationResult


@pytest.fixture
def mock_guide():
    """Create a mocked WellnessGuide."""
    guide = Mock()
    guide.generate_response.return_value = "I can help with that."
    guide.generate_response_stream.return_value = iter(["I ", "can ", "help."])
    guide.last_risk_assessment = None
    guide.last_policy_action = None
    guide._last_streamed_response = ""
    guide.reset_session.return_value = None
    guide.get_session_summary.return_value = {"turns": 0, "domains": []}
    return guide


@pytest.fixture
def mock_tracker():
    """Create a mocked WellnessTracker."""
    tracker = Mock()
    tracker.should_enforce_cooldown.return_value = (False, None)
    tracker.record_session_intent.return_value = None
    tracker.record_task_category.return_value = None
    tracker.should_show_graduation_prompt.return_value = (False, None)
    tracker.record_graduation_shown.return_value = None
    tracker.record_graduation_dismissal.return_value = None
    tracker.record_graduation_accepted.return_value = None
    return tracker


@pytest.fixture
def mock_network():
    """Create a mocked TrustedNetwork."""
    network = Mock()
    network.get_all_people.return_value = []
    network.get_people_for_domain.return_value = []
    return network


@pytest.fixture
def mock_loader():
    """Create a mocked ScenarioLoader."""
    loader = Mock()
    loader.get_connection_responses.return_value = []
    loader.get_graduation_category.return_value = None
    loader.get_graduation_settings.return_value = {"max_dismissals": 3}
    loader.get_graduation_prompts.return_value = []
    loader.get_isolation_signals.return_value = [
        "there is no one",
        "i have no one",
        "nobody to talk to",
        "no one really",
    ]
    return loader


@pytest.fixture
def mock_classifier():
    """Create a mocked RiskClassifier."""
    classifier = Mock()
    classifier.is_connection_seeking.return_value = (False, None)
    classifier.detect_intent.return_value = ("practical", 0.8)
    classifier.detect_intent_shift.return_value = None
    classifier.detect_task_category.return_value = (None, 0.0)
    return classifier


@pytest.fixture
def session(mock_guide, mock_tracker, mock_network, mock_loader, mock_classifier):
    """Create a ConversationSession with all dependencies mocked."""
    with (
        patch("models.conversation_session.RiskClassifier", return_value=mock_classifier),
        patch("models.conversation_session.get_scenario_loader", return_value=mock_loader),
    ):
        s = ConversationSession(
            guide=mock_guide,
            tracker=mock_tracker,
            network=mock_network,
            wellness_mode="Balanced",
        )
    return s


class TestConversationSessionInit:
    """Tests for ConversationSession initialization."""

    def test_init_stores_dependencies(self, session, mock_guide, mock_tracker, mock_network):
        assert session.guide is mock_guide
        assert session.tracker is mock_tracker
        assert session.network is mock_network

    def test_init_default_wellness_mode(self, session):
        assert session.wellness_mode == "Balanced"

    def test_init_custom_wellness_mode(self, mock_guide, mock_tracker, mock_network):
        with (
            patch("models.conversation_session.RiskClassifier"),
            patch("models.conversation_session.get_scenario_loader"),
        ):
            s = ConversationSession(
                guide=mock_guide,
                tracker=mock_tracker,
                network=mock_network,
                wellness_mode="Gentle",
            )
        assert s.wellness_mode == "Gentle"

    def test_init_empty_messages(self, session):
        assert session.messages == []

    def test_init_no_session_intent(self, session):
        assert session.session_intent is None

    def test_init_no_pending_shift(self, session):
        assert session.pending_shift is None
        assert session.acknowledged_shift is False

    def test_init_no_pending_graduation(self, session):
        assert session.pending_graduation is None
        assert session.graduation_shown_this_session is False

    def test_init_no_last_task_category(self, session):
        assert session.last_task_category is None

    def test_init_no_handoff_state(self, session):
        assert session.pending_handoff_for_outcome is None
        assert session.pending_handoff_info is None


class TestTurnCount:
    """Tests for the turn_count property."""

    def test_turn_count_empty(self, session):
        assert session.turn_count == 0

    def test_turn_count_one_user_message(self, session):
        session.messages.append({"role": "user", "content": "hello"})
        assert session.turn_count == 1

    def test_turn_count_ignores_assistant_messages(self, session):
        session.messages.append({"role": "user", "content": "hello"})
        session.messages.append({"role": "assistant", "content": "hi"})
        assert session.turn_count == 1

    def test_turn_count_multiple_user_messages(self, session):
        for i in range(5):
            session.messages.append({"role": "user", "content": f"msg {i}"})
            session.messages.append({"role": "assistant", "content": f"reply {i}"})
        assert session.turn_count == 5


class TestProcessMessage:
    """Tests for process_message() pipeline."""

    def test_basic_message_returns_conversation_result(self, session):
        result = session.process_message("Help me write an email")
        assert isinstance(result, ConversationResult)

    def test_response_comes_from_guide(self, session, mock_guide):
        mock_guide.generate_response.return_value = "Here is your email."
        result = session.process_message("Write an email")
        assert result.response == "Here is your email."

    def test_user_message_added_to_history(self, session):
        session.process_message("Hello there")
        assert session.messages[0] == {"role": "user", "content": "Hello there"}

    def test_assistant_response_added_to_history(self, session, mock_guide):
        mock_guide.generate_response.return_value = "Hi!"
        session.process_message("Hello")
        assert session.messages[1] == {"role": "assistant", "content": "Hi!"}

    def test_turn_count_increments(self, session):
        session.process_message("First message")
        assert session.turn_count == 1
        session.process_message("Second message")
        assert session.turn_count == 2

    def test_guide_called_with_correct_args(self, session, mock_guide):
        session.process_message("Test input")
        mock_guide.generate_response.assert_called_once_with(
            "Test input",
            "Balanced",
            session.messages,
            wellness_tracker=session.tracker,
            connection_steering=session.connection_steering,
        )

    def test_result_includes_risk_assessment(self, session, mock_guide):
        mock_guide.last_risk_assessment = {"domain": "logistics", "risk_weight": 1.0}
        result = session.process_message("Help me code")
        assert result.risk_assessment == {"domain": "logistics", "risk_weight": 1.0}

    def test_result_includes_policy_action(self, session, mock_guide):
        mock_guide.last_policy_action = {"type": "turn_limit", "domain": "emotional"}
        result = session.process_message("I feel sad")
        assert result.policy_action == {"type": "turn_limit", "domain": "emotional"}

    def test_should_rerun_true_when_policy_action(self, session, mock_guide):
        mock_guide.last_policy_action = {"type": "some_action"}
        result = session.process_message("test")
        assert result.should_rerun is True

    def test_should_rerun_false_when_no_policy_or_shift(self, session, mock_guide):
        mock_guide.last_policy_action = None
        result = session.process_message("test")
        assert result.should_rerun is False


class TestCooldown:
    """Tests for cooldown enforcement in process_message."""

    def test_cooldown_returns_early(self, session, mock_tracker):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Too many sessions today")
        result = session.process_message("Hello")
        assert result.is_cooldown_active is True
        assert result.cooldown_message == "Too many sessions today"
        assert result.response == ""

    def test_cooldown_skips_guide(self, session, mock_tracker, mock_guide):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Cooldown")
        session.process_message("Hello")
        mock_guide.generate_response.assert_not_called()

    def test_cooldown_suggests_person_when_available(self, session, mock_tracker, mock_network):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Cooldown")
        mock_network.get_all_people.return_value = [{"name": "Alice"}]
        result = session.process_message("Hello")
        assert result.suggested_handoff_person == "Alice"

    def test_cooldown_no_person_when_network_empty(self, session, mock_tracker, mock_network):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Cooldown")
        mock_network.get_all_people.return_value = []
        result = session.process_message("Hello")
        assert result.suggested_handoff_person is None

    def test_cooldown_still_records_user_message(self, session, mock_tracker):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Cooldown")
        session.process_message("Hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"

    def test_cooldown_turn_count_in_result(self, session, mock_tracker):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Cooldown")
        result = session.process_message("Hello")
        assert result.turn_count == 1


class TestFirstTurnConnectionSeeking:
    """Tests for connection-seeking detection on first turn."""

    def test_connection_seeking_returns_redirect(self, session):
        session.classifier.is_connection_seeking.return_value = (True, "loneliness")
        session.loader.get_connection_responses.return_value = [
            "It sounds like you're reaching out."
        ]
        result = session.process_message("I just need someone to talk to")
        assert result.pending_connection_redirect == {"type": "loneliness"}
        assert result.should_rerun is True

    def test_connection_seeking_sets_intent(self, session, mock_tracker):
        session.classifier.is_connection_seeking.return_value = (True, "loneliness")
        session.loader.get_connection_responses.return_value = ["Response"]
        session.process_message("I'm lonely")
        assert session.session_intent == "connection"
        mock_tracker.record_session_intent.assert_called_once()

    def test_connection_ai_relationship_type(self, session):
        session.classifier.is_connection_seeking.return_value = (True, "ai_relationship")
        session.loader.get_connection_responses.return_value = ["I'm an AI."]
        result = session.process_message("Can you be my friend?")
        session.loader.get_connection_responses.assert_called_with("ai_relationship")

    def test_connection_seeking_adds_response_to_history(self, session):
        session.classifier.is_connection_seeking.return_value = (True, "loneliness")
        session.loader.get_connection_responses.return_value = ["A response"]
        session.process_message("I need someone")
        assert session.messages[-1] == {"role": "assistant", "content": "A response"}

    def test_connection_seeking_no_responses_falls_through(self, session, mock_guide):
        session.classifier.is_connection_seeking.return_value = (True, "loneliness")
        session.loader.get_connection_responses.return_value = []
        # Should fall through to normal generate_response
        result = session.process_message("I'm lonely")
        mock_guide.generate_response.assert_called_once()


class TestFirstTurnIntentDetection:
    """Tests for auto-intent detection on first turn (non-connection)."""

    def test_high_confidence_sets_intent(self, session, mock_tracker):
        session.classifier.is_connection_seeking.return_value = (False, None)
        session.classifier.detect_intent.return_value = ("practical", 0.9)
        session.process_message("Help me write code")
        assert session.session_intent == "practical"
        mock_tracker.record_session_intent.assert_called_once_with("practical", auto_detected=True)

    def test_low_confidence_does_not_set_intent(self, session, mock_tracker):
        session.classifier.is_connection_seeking.return_value = (False, None)
        session.classifier.detect_intent.return_value = ("emotional", 0.4)
        session.process_message("Hey")
        assert session.session_intent is None
        mock_tracker.record_session_intent.assert_not_called()

    def test_exactly_threshold_sets_intent(self, session):
        session.classifier.is_connection_seeking.return_value = (False, None)
        session.classifier.detect_intent.return_value = ("processing", 0.6)
        session.process_message("Something")
        assert session.session_intent == "processing"

    def test_intent_detection_only_on_first_turn(self, session):
        """Intent detection should not run after the first turn."""
        session.classifier.is_connection_seeking.return_value = (False, None)
        session.classifier.detect_intent.return_value = ("practical", 0.9)
        session.process_message("First message")
        session.classifier.detect_intent.reset_mock()

        # Second message - should not trigger intent detection
        session.process_message("Second message")
        session.classifier.detect_intent.assert_not_called()


class TestIntentShiftDetection:
    """Tests for intent shift detection after first turn."""

    def test_no_shift_when_no_session_intent(self, session):
        session.session_intent = None
        # Add enough messages so len > 2
        session.messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        session.process_message("New message")
        session.classifier.detect_intent_shift.assert_not_called()

    def test_shift_detected_sets_pending(self, session):
        session.session_intent = "practical"
        session.messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        session.classifier.detect_intent_shift.return_value = {
            "is_concerning": True,
            "to_intent": "emotional",
        }
        result = session.process_message("I'm actually really stressed")
        assert session.pending_shift == {
            "is_concerning": True,
            "to_intent": "emotional",
        }
        assert result.should_rerun is True

    def test_non_concerning_shift_ignored(self, session):
        session.session_intent = "practical"
        session.messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        session.classifier.detect_intent_shift.return_value = {
            "is_concerning": False,
            "to_intent": "emotional",
        }
        session.process_message("Something")
        assert session.pending_shift is None

    def test_no_shift_when_already_acknowledged(self, session):
        session.session_intent = "practical"
        session.acknowledged_shift = True
        session.messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        session.process_message("test")
        session.classifier.detect_intent_shift.assert_not_called()

    def test_shift_not_checked_when_messages_too_few(self, session):
        session.session_intent = "practical"
        # Only 1 message in history before process_message adds the new one
        session.messages = [{"role": "user", "content": "a"}]
        session.process_message("test")
        # After adding user message, len == 2 which is not > 2
        session.classifier.detect_intent_shift.assert_not_called()


class TestHandoffSuggestion:
    """Tests for handoff suggestions based on policy action domain."""

    def test_handoff_suggested_for_relationships(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "relationships"}
        mock_network.get_people_for_domain.return_value = [{"name": "Bob"}]
        result = session.process_message("Should I break up?")
        assert result.suggested_handoff_person == "Bob"
        assert result.suggested_handoff_domain == "relationships"

    def test_handoff_suggested_for_money(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "money"}
        mock_network.get_people_for_domain.return_value = [{"name": "Carol"}]
        result = session.process_message("Should I invest?")
        assert result.suggested_handoff_person == "Carol"
        assert result.suggested_handoff_domain == "money"

    def test_handoff_suggested_for_health(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "health"}
        mock_network.get_people_for_domain.return_value = [{"name": "Dr. Smith"}]
        result = session.process_message("Should I get surgery?")
        assert result.suggested_handoff_person == "Dr. Smith"

    def test_handoff_suggested_for_spirituality(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "spirituality"}
        mock_network.get_people_for_domain.return_value = [{"name": "Pastor Lee"}]
        result = session.process_message("Is this God's plan?")
        assert result.suggested_handoff_person == "Pastor Lee"

    def test_no_handoff_for_logistics(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "logistics"}
        result = session.process_message("Write an email")
        assert result.suggested_handoff_person is None
        mock_network.get_people_for_domain.assert_not_called()

    def test_no_handoff_when_no_people(self, session, mock_guide, mock_network):
        mock_guide.last_policy_action = {"domain": "health"}
        mock_network.get_people_for_domain.return_value = []
        result = session.process_message("Medical question")
        assert result.suggested_handoff_person is None

    def test_no_handoff_when_no_policy_action(self, session, mock_guide):
        mock_guide.last_policy_action = None
        result = session.process_message("Hello")
        assert result.suggested_handoff_person is None


class TestGraduationChecking:
    """Tests for graduation eligibility checking in process_message."""

    def test_graduation_check_for_logistics_domain(self, session, mock_guide, mock_tracker):
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("email_writing", 0.9)
        session.loader.get_graduation_category.return_value = {"threshold": 10}
        session.loader.get_graduation_settings.return_value = {"max_dismissals": 3}
        mock_tracker.should_show_graduation_prompt.return_value = (True, "threshold_met")
        session.loader.get_graduation_prompts.return_value = ["You've mastered this!"]

        result = session.process_message("Write another email")
        assert result.pending_graduation is not None
        assert result.pending_graduation["category"] == "email_writing"
        assert result.pending_graduation["prompt"] == "You've mastered this!"

    def test_no_graduation_for_non_logistics(self, session, mock_guide):
        mock_guide.last_risk_assessment = {"domain": "emotional"}
        session.process_message("I feel sad")
        session.classifier.detect_task_category.assert_not_called()

    def test_no_graduation_low_confidence_category(self, session, mock_guide):
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("email_writing", 0.3)
        session.process_message("Write email")
        session.loader.get_graduation_category.assert_not_called()

    def test_no_graduation_when_already_shown(self, session, mock_guide, mock_tracker):
        session.graduation_shown_this_session = True
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("email_writing", 0.9)
        session.process_message("Write email")
        session.loader.get_graduation_category.assert_not_called()

    def test_no_graduation_when_tracker_says_no(self, session, mock_guide, mock_tracker):
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("email_writing", 0.9)
        session.loader.get_graduation_category.return_value = {"threshold": 10}
        session.loader.get_graduation_settings.return_value = {"max_dismissals": 3}
        mock_tracker.should_show_graduation_prompt.return_value = (False, "not_enough")
        session.process_message("Write email")
        assert session.pending_graduation is None

    def test_task_category_recorded(self, session, mock_guide, mock_tracker):
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("coding", 0.8)
        session.process_message("Fix this bug")
        mock_tracker.record_task_category.assert_called_once_with("coding")
        assert session.last_task_category == "coding"


class TestProcessMessageStream:
    """Tests for process_message_stream() pipeline."""

    def test_returns_conversation_result_with_stream(self, session, mock_guide):
        result = session.process_message_stream("Help me code")
        assert isinstance(result, ConversationResult)
        assert result.response_stream is not None
        assert result.is_streaming is True

    def test_stream_result_has_empty_response(self, session):
        result = session.process_message_stream("Hello")
        assert result.response == ""

    def test_user_message_added_to_history(self, session):
        session.process_message_stream("Hello there")
        assert session.messages[0] == {"role": "user", "content": "Hello there"}

    def test_pending_stream_input_stored(self, session):
        session.process_message_stream("Some input")
        assert session._pending_stream_input == "Some input"

    def test_guide_stream_called_with_correct_args(self, session, mock_guide):
        session.process_message_stream("Test input")
        mock_guide.generate_response_stream.assert_called_once_with(
            "Test input",
            "Balanced",
            session.messages,
            wellness_tracker=session.tracker,
            connection_steering=session.connection_steering,
        )

    def test_stream_cooldown_returns_early(self, session, mock_tracker, mock_guide):
        mock_tracker.should_enforce_cooldown.return_value = (True, "Too many sessions")
        result = session.process_message_stream("Hello")
        assert result.is_cooldown_active is True
        assert result.cooldown_message == "Too many sessions"
        assert result.response_stream is None
        mock_guide.generate_response_stream.assert_not_called()

    def test_stream_connection_seeking_returns_early(self, session, mock_guide):
        session.classifier.is_connection_seeking.return_value = (True, "loneliness")
        session.loader.get_connection_responses.return_value = ["You're not alone."]
        result = session.process_message_stream("I'm lonely")
        assert result.pending_connection_redirect == {"type": "loneliness"}
        assert result.response == "You're not alone."
        assert result.response_stream is None
        mock_guide.generate_response_stream.assert_not_called()

    def test_stream_intent_detection_on_first_turn(self, session, mock_tracker):
        session.classifier.is_connection_seeking.return_value = (False, None)
        session.classifier.detect_intent.return_value = ("practical", 0.85)
        session.process_message_stream("Write code for me")
        assert session.session_intent == "practical"

    def test_stream_intent_shift_detection(self, session):
        session.session_intent = "practical"
        session.messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        session.classifier.detect_intent_shift.return_value = {
            "is_concerning": True,
            "to_intent": "emotional",
        }
        result = session.process_message_stream("I'm breaking down")
        assert result.pending_shift is not None


class TestFinalizeStream:
    """Tests for finalize_stream() after consuming the token stream."""

    def test_finalize_adds_response_to_history(self, session, mock_guide):
        session.process_message_stream("Hello")
        mock_guide._last_streamed_response = "The full response"
        result = session.finalize_stream()
        assert session.messages[-1] == {
            "role": "assistant",
            "content": "The full response",
        }

    def test_finalize_returns_full_response(self, session, mock_guide):
        session.process_message_stream("Hello")
        mock_guide._last_streamed_response = "Complete answer"
        result = session.finalize_stream()
        assert result.response == "Complete answer"
        assert result.response_stream is None

    def test_finalize_includes_risk_assessment(self, session, mock_guide):
        session.process_message_stream("Test")
        mock_guide._last_streamed_response = "Response"
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        result = session.finalize_stream()
        assert result.risk_assessment == {"domain": "logistics"}

    def test_finalize_includes_policy_action(self, session, mock_guide):
        session.process_message_stream("Test")
        mock_guide._last_streamed_response = "Response"
        mock_guide.last_policy_action = {"type": "crisis_stop"}
        result = session.finalize_stream()
        assert result.policy_action == {"type": "crisis_stop"}

    def test_finalize_graduation_check(self, session, mock_guide, mock_tracker):
        session._pending_stream_input = "Write an email"
        mock_guide._last_streamed_response = "Here is your email."
        mock_guide.last_risk_assessment = {"domain": "logistics"}
        session.classifier.detect_task_category.return_value = ("email_writing", 0.9)
        session.loader.get_graduation_category.return_value = {"threshold": 5}
        session.loader.get_graduation_settings.return_value = {"max_dismissals": 3}
        mock_tracker.should_show_graduation_prompt.return_value = (True, "threshold_met")
        session.loader.get_graduation_prompts.return_value = ["Great job!"]

        result = session.finalize_stream()
        assert result.pending_graduation is not None
        assert result.pending_graduation["category"] == "email_writing"

    def test_finalize_handoff_suggestion(self, session, mock_guide, mock_network):
        session._pending_stream_input = "Test"
        mock_guide._last_streamed_response = "Response"
        mock_guide.last_policy_action = {"domain": "health"}
        mock_network.get_people_for_domain.return_value = [{"name": "Dr. Jones"}]
        result = session.finalize_stream()
        assert result.suggested_handoff_person == "Dr. Jones"
        assert result.suggested_handoff_domain == "health"

    def test_finalize_should_rerun_with_policy(self, session, mock_guide):
        session._pending_stream_input = "Test"
        mock_guide._last_streamed_response = "Response"
        mock_guide.last_policy_action = {"type": "something"}
        result = session.finalize_stream()
        assert result.should_rerun is True

    def test_finalize_empty_streamed_response(self, session, mock_guide):
        session.process_message_stream("Hello")
        mock_guide._last_streamed_response = ""
        result = session.finalize_stream()
        assert result.response == ""
        assert session.messages[-1]["content"] == ""


class TestAcknowledgeIntentShift:
    """Tests for acknowledge_intent_shift()."""

    def test_accept_shift_updates_intent(self, session):
        session.pending_shift = {"to_intent": "emotional", "is_concerning": True}
        session.acknowledge_intent_shift(accept_shift=True)
        assert session.session_intent == "emotional"
        assert session.acknowledged_shift is True
        assert session.pending_shift is None

    def test_reject_shift_keeps_original_intent(self, session):
        session.session_intent = "practical"
        session.pending_shift = {"to_intent": "emotional", "is_concerning": True}
        session.acknowledge_intent_shift(accept_shift=False)
        assert session.session_intent == "practical"
        assert session.acknowledged_shift is True
        assert session.pending_shift is None

    def test_accept_shift_defaults_to_emotional(self, session):
        """If pending_shift has no to_intent, defaults to INTENT_EMOTIONAL."""
        session.pending_shift = {"is_concerning": True}
        session.acknowledge_intent_shift(accept_shift=True)
        assert session.session_intent == "emotional"

    def test_accept_with_no_pending_shift(self, session):
        session.pending_shift = None
        session.session_intent = "practical"
        session.acknowledge_intent_shift(accept_shift=True)
        # Should not change intent when pending_shift is None
        assert session.session_intent == "practical"
        assert session.acknowledged_shift is True


class TestGraduationActions:
    """Tests for dismiss_graduation() and accept_graduation()."""

    def test_dismiss_graduation_records_dismissal(self, session, mock_tracker):
        session.pending_graduation = {"category": "email_writing", "prompt": "Great!"}
        session.dismiss_graduation()
        mock_tracker.record_graduation_dismissal.assert_called_once_with("email_writing")
        assert session.graduation_shown_this_session is True
        assert session.pending_graduation is None

    def test_dismiss_graduation_no_pending(self, session, mock_tracker):
        session.pending_graduation = None
        session.dismiss_graduation()
        mock_tracker.record_graduation_dismissal.assert_not_called()
        assert session.graduation_shown_this_session is True

    def test_accept_graduation_records_acceptance(self, session, mock_tracker):
        session.pending_graduation = {"category": "coding", "prompt": "Well done!"}
        session.accept_graduation()
        mock_tracker.record_graduation_accepted.assert_called_once_with("coding")
        assert session.graduation_shown_this_session is True

    def test_accept_graduation_no_pending(self, session, mock_tracker):
        session.pending_graduation = None
        session.accept_graduation()
        mock_tracker.record_graduation_accepted.assert_not_called()
        assert session.graduation_shown_this_session is True


class TestReset:
    """Tests for reset() clearing all session state."""

    def test_reset_clears_messages(self, session):
        session.messages = [{"role": "user", "content": "hi"}]
        session.reset()
        assert session.messages == []

    def test_reset_clears_intent(self, session):
        session.session_intent = "practical"
        session.reset()
        assert session.session_intent is None

    def test_reset_clears_pending_shift(self, session):
        session.pending_shift = {"to_intent": "emotional"}
        session.acknowledged_shift = True
        session.reset()
        assert session.pending_shift is None
        assert session.acknowledged_shift is False

    def test_reset_clears_graduation(self, session):
        session.pending_graduation = {"category": "coding"}
        session.graduation_shown_this_session = True
        session.reset()
        assert session.pending_graduation is None
        assert session.graduation_shown_this_session is False

    def test_reset_clears_task_category(self, session):
        session.last_task_category = "email_writing"
        session.reset()
        assert session.last_task_category is None

    def test_reset_clears_handoff_state(self, session):
        session.pending_handoff_for_outcome = "some_outcome"
        session.pending_handoff_info = {"template": "checking_in"}
        session.reset()
        assert session.pending_handoff_for_outcome is None
        assert session.pending_handoff_info is None

    def test_reset_calls_guide_reset(self, session, mock_guide):
        session.reset()
        mock_guide.reset_session.assert_called_once()


class TestGetSessionSummary:
    """Tests for get_session_summary() delegation."""

    def test_delegates_to_guide(self, session, mock_guide):
        mock_guide.get_session_summary.return_value = {
            "turns": 5,
            "domains": ["logistics"],
        }
        result = session.get_session_summary()
        assert result == {"turns": 5, "domains": ["logistics"]}
        mock_guide.get_session_summary.assert_called_once()


class TestConversationResultDataclass:
    """Tests for the ConversationResult dataclass itself."""

    def test_minimal_construction(self):
        result = ConversationResult(response="Hello")
        assert result.response == "Hello"
        assert result.risk_assessment is None
        assert result.policy_action is None
        assert result.is_cooldown_active is False
        assert result.turn_count == 0
        assert result.should_rerun is False
        assert result.response_stream is None

    def test_is_streaming_false_by_default(self):
        result = ConversationResult(response="test")
        assert result.is_streaming is False

    def test_is_streaming_true_with_stream(self):
        result = ConversationResult(response="", response_stream=iter(["a", "b"]))
        assert result.is_streaming is True

    def test_all_fields(self):
        result = ConversationResult(
            response="answer",
            risk_assessment={"domain": "health"},
            policy_action={"type": "turn_limit"},
            pending_shift={"to_intent": "emotional"},
            pending_graduation={"category": "coding"},
            pending_connection_redirect={"type": "loneliness"},
            suggested_handoff_person="Alice",
            suggested_handoff_domain="health",
            is_cooldown_active=True,
            cooldown_message="Too many sessions",
            turn_count=5,
            should_rerun=True,
        )
        assert result.response == "answer"
        assert result.risk_assessment["domain"] == "health"
        assert result.policy_action["type"] == "turn_limit"
        assert result.pending_shift["to_intent"] == "emotional"
        assert result.pending_graduation["category"] == "coding"
        assert result.pending_connection_redirect["type"] == "loneliness"
        assert result.suggested_handoff_person == "Alice"
        assert result.suggested_handoff_domain == "health"
        assert result.is_cooldown_active is True
        assert result.cooldown_message == "Too many sessions"
        assert result.turn_count == 5
        assert result.should_rerun is True


# ---------------------------------------------------------------------------
# ConnectionSteering dataclass
# ---------------------------------------------------------------------------


class TestConnectionSteering:
    """Tests for ConnectionSteering."""

    def test_default_state_is_inactive(self):
        cs = ConnectionSteering()
        assert cs.active is False
        assert cs.first_detected_turn == 0

    def test_activate_sets_active_and_turn(self):
        cs = ConnectionSteering()
        cs.activate(turn_count=3)
        assert cs.active is True
        assert cs.first_detected_turn == 3


# ---------------------------------------------------------------------------
# Connection steering integration in ConversationSession
# ---------------------------------------------------------------------------


class TestConnectionSteeringIntegration:
    """Tests for isolation detection and steering activation in ConversationSession."""

    def test_isolation_not_active_by_default(self, session):
        assert session.connection_steering.active is False

    def test_check_isolation_signals_direct_match(self, session):
        assert session._check_isolation_signals("there is no one to help me") is True

    def test_check_isolation_signals_no_match(self, session):
        assert session._check_isolation_signals("help me write an email") is False

    def test_isolation_activates_steering_in_process_message(
        self, session, mock_guide, mock_loader, mock_classifier
    ):
        mock_guide.generate_response.return_value = "Here's some help."
        mock_guide.last_risk_assessment = {"domain": "logistics", "isolation_level": "none"}
        mock_guide.last_policy_action = None
        mock_classifier.is_connection_seeking.return_value = (False, None)
        mock_classifier.detect_intent.return_value = ("practical", 0.8)
        mock_classifier.detect_intent_shift.return_value = None
        mock_classifier.detect_task_category.return_value = (None, 0.0)
        mock_loader.get_graduation_category.return_value = None

        session.process_message("Help me with this task, there is no one I can ask")

        assert session.connection_steering.active is True

    def test_steering_passed_to_generate_response(
        self, session, mock_guide, mock_loader, mock_classifier
    ):
        mock_guide.generate_response.return_value = "Here's some help."
        mock_guide.last_risk_assessment = {"domain": "logistics", "isolation_level": "none"}
        mock_guide.last_policy_action = None
        mock_classifier.is_connection_seeking.return_value = (False, None)
        mock_classifier.detect_intent.return_value = ("practical", 0.8)
        mock_classifier.detect_intent_shift.return_value = None
        mock_classifier.detect_task_category.return_value = (None, 0.0)
        mock_loader.get_graduation_category.return_value = None

        session.process_message("I have no one to ask. Help me write this email.")

        _, call_kwargs = mock_guide.generate_response.call_args
        assert "connection_steering" in call_kwargs
        assert call_kwargs["connection_steering"].active is True

    def test_reset_clears_steering_state(self, session):
        session.connection_steering.activate(turn_count=1)
        session.reset()
        assert session.connection_steering.active is False

    def test_llm_isolation_detection_activates_steering_after_response(
        self, session, mock_guide, mock_loader, mock_classifier
    ):
        """LLM-detected isolation (no keyword match) activates steering for next turn."""
        mock_guide.generate_response.return_value = "Here's some help."
        mock_guide.last_risk_assessment = {
            "domain": "logistics",
            "isolation_level": "passive",
        }
        mock_guide.last_policy_action = None
        mock_classifier.is_connection_seeking.return_value = (False, None)
        mock_classifier.detect_intent.return_value = ("practical", 0.8)
        mock_classifier.detect_intent_shift.return_value = None
        mock_classifier.detect_task_category.return_value = (None, 0.0)
        mock_loader.get_graduation_category.return_value = None

        # Message with no keyword match - relies on LLM result
        session.process_message("I just manage things by myself")

        # Steering activates post-response from LLM result
        assert session.connection_steering.active is True


# ---------------------------------------------------------------------------
# Performance logging
# ---------------------------------------------------------------------------


class TestPerfLogging:
    """Tests for [PERF] structured log line emitted per message."""

    def test_perf_logged_after_process_message(
        self, session, mock_guide, mock_loader, mock_classifier
    ):
        mock_guide.generate_response.return_value = "Done."
        mock_guide.last_risk_assessment = {"domain": "logistics", "classification_method": "llm"}
        mock_guide.last_policy_action = None
        mock_guide.risk_classifier = MagicMock()
        mock_guide.risk_classifier._llm_classifier = None
        mock_guide.ollama_client = MagicMock()
        mock_guide.ollama_client.last_generate_duration = 1.5
        mock_classifier.is_connection_seeking.return_value = (False, None)
        mock_classifier.detect_intent.return_value = ("practical", 0.8)
        mock_classifier.detect_intent_shift.return_value = None
        mock_classifier.detect_task_category.return_value = (None, 0.0)
        mock_loader.get_graduation_category.return_value = None

        import logging

        with patch.object(logging.getLogger("models.conversation_session"), "info") as mock_log:
            session.process_message("help me write an email")

        logged = [str(c) for c in mock_log.call_args_list]
        assert any("[PERF]" in msg for msg in logged)

    def test_perf_log_contains_domain_and_method(
        self, session, mock_guide, mock_loader, mock_classifier
    ):
        mock_guide.generate_response.return_value = "Done."
        mock_guide.last_risk_assessment = {
            "domain": "emotional",
            "classification_method": "keyword",
        }
        mock_guide.last_policy_action = None
        mock_guide.risk_classifier = MagicMock()
        mock_guide.risk_classifier._llm_classifier = None
        mock_guide.ollama_client = MagicMock()
        mock_guide.ollama_client.last_generate_duration = 0.5
        mock_classifier.is_connection_seeking.return_value = (False, None)
        mock_classifier.detect_intent.return_value = ("emotional", 0.8)
        mock_classifier.detect_intent_shift.return_value = None
        mock_classifier.detect_task_category.return_value = (None, 0.0)
        mock_loader.get_graduation_category.return_value = None

        import logging

        with patch.object(logging.getLogger("models.conversation_session"), "info") as mock_log:
            session.process_message("I feel sad")

        perf_lines = [str(c) for c in mock_log.call_args_list if "[PERF]" in str(c)]
        assert len(perf_lines) == 1
        assert "emotional" in perf_lines[0]
        assert "keyword" in perf_lines[0]
