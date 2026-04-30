"""
ConversationSession - Framework-agnostic conversation session manager.

Owns all conversation state and orchestrates the message processing pipeline.
Can be driven by any interface adapter (Streamlit, CLI, messaging, etc.).

This is the "soul" of empathySync — the reusable core that any project
can import to get safety-aware, restraint-first conversation handling.
"""

import random
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from models.ai_wellness_guide import WellnessGuide
from models.risk_classifier import (
    RiskClassifier,
    INTENT_CONNECTION,
    INTENT_PRACTICAL,
    INTENT_PROCESSING,
    INTENT_EMOTIONAL,
)
from models.conversation_result import ConversationResult
from utils.wellness_tracker import WellnessTracker
from utils.trusted_network import TrustedNetwork
from utils.scenario_loader import get_scenario_loader

logger = logging.getLogger(__name__)


@dataclass
class ConnectionSteering:
    """
    Session-level flag for connection steering.

    When isolation is detected ("there is no one really"), this activates and
    persists for the session, injecting a background warmth modifier into every
    subsequent response. The modifier changes tone and texture - not topic.
    The user should not feel steered; they should just feel slightly more noticed.
    """

    active: bool = False
    first_detected_turn: int = 0

    def activate(self, turn_count: int) -> None:
        """Activate steering, recording when it was first triggered."""
        self.active = True
        self.first_detected_turn = turn_count


def _load_confidence_threshold() -> float:
    """Load intent detection confidence threshold from system_defaults.yaml, fallback to 0.6."""
    try:
        loader = get_scenario_loader()
        defaults = loader.get_system_defaults()
        return float(defaults.get("classification", {}).get("confidence_threshold", 0.6))
    except Exception:
        return 0.6


# Minimum confidence for auto-detected intent and task category to be accepted.
_CONFIDENCE_THRESHOLD = _load_confidence_threshold()


class ConversationSession:
    """
    Framework-agnostic conversation session manager.

    Owns all conversation state and orchestrates the message processing
    pipeline. Returns structured ConversationResult objects — never
    renders anything directly.
    """

    def __init__(
        self,
        guide: WellnessGuide,
        tracker: WellnessTracker,
        network: TrustedNetwork,
        wellness_mode: str = "Balanced",
    ):
        self.guide = guide
        self.tracker = tracker
        self.network = network
        self.wellness_mode = wellness_mode
        self.classifier = RiskClassifier()
        self.loader = get_scenario_loader()

        # Conversation state (extracted from st.session_state)
        self.messages: List[Dict] = []
        self.session_intent: Optional[str] = None
        self.pending_shift: Optional[Dict] = None
        self.acknowledged_shift: bool = False
        self.pending_graduation: Optional[Dict] = None
        self.graduation_shown_this_session: bool = False
        self.last_task_category: Optional[str] = None

        # Handoff state
        self.pending_handoff_for_outcome: Optional[str] = None
        self.pending_handoff_info: Optional[Dict] = None

        # Connection steering state
        self.connection_steering = ConnectionSteering()

    @property
    def turn_count(self) -> int:
        """Number of user messages in this session."""
        return sum(1 for m in self.messages if m["role"] == "user")

    def process_message(self, user_input: str) -> ConversationResult:
        """
        Process a user message through the full conversation pipeline.

        This is the single entry point for all message processing.
        The safety pipeline in WellnessGuide.generate_response() is
        called internally — callers don't need to manage safety logic.

        Args:
            user_input: The user's message text.

        Returns:
            ConversationResult with the response and all metadata.
        """
        t_msg_start = time.perf_counter()

        # Add user message to history
        self.messages.append({"role": "user", "content": user_input})

        # Step 1: Check cooldown
        should_cooldown, cooldown_reason = self.tracker.should_enforce_cooldown()
        if should_cooldown:
            suggested_person = None
            people = self.network.get_all_people()
            if people:
                person = random.choice(people)
                suggested_person = person.get("name")

            return ConversationResult(
                response="",
                is_cooldown_active=True,
                cooldown_message=cooldown_reason,
                suggested_handoff_person=suggested_person,
                turn_count=self.turn_count,
            )

        # Step 2: First-turn processing
        if self.turn_count == 1:
            # Check for connection-seeking
            is_connection, connection_type = self.classifier.is_connection_seeking(user_input)
            if is_connection:
                self.tracker.record_session_intent(INTENT_CONNECTION, auto_detected=True)
                self.session_intent = INTENT_CONNECTION

                # Get connection response
                if connection_type == "ai_relationship":
                    responses = self.loader.get_connection_responses("ai_relationship")
                else:
                    responses = self.loader.get_connection_responses(connection_type)

                if responses:
                    response = random.choice(responses)
                    self.messages.append({"role": "assistant", "content": response})

                    return ConversationResult(
                        response=response,
                        pending_connection_redirect={"type": connection_type},
                        should_rerun=True,
                        turn_count=self.turn_count,
                    )
            else:
                # Auto-detect intent from first message
                detected_intent, confidence = self.classifier.detect_intent(user_input)
                if confidence >= _CONFIDENCE_THRESHOLD:
                    self.tracker.record_session_intent(detected_intent, auto_detected=True)
                    self.session_intent = detected_intent

        # Step 3: Intent shift detection (after first turn)
        if self.session_intent and len(self.messages) > 2 and not self.acknowledged_shift:
            shift = self.classifier.detect_intent_shift(
                self.messages, self.session_intent, user_input
            )
            if shift and shift.get("is_concerning"):
                self.pending_shift = shift

        # Step 3.5: Isolation detection - keyword fast-path before LLM call
        # so steering context can be injected into this response immediately.
        if not self.connection_steering.active:
            if self._check_isolation_signals(user_input):
                self.connection_steering.activate(self.turn_count)

        # Step 4: Generate response via WellnessGuide safety pipeline
        response = self.guide.generate_response(
            user_input,
            self.wellness_mode,
            self.messages,
            wellness_tracker=self.tracker,
            connection_steering=self.connection_steering,
        )

        self.messages.append({"role": "assistant", "content": response})

        # Step 4.5: Post-response isolation checks
        # Check LLM-detected isolation (for cases keyword fast-path missed)
        if not self.connection_steering.active and self.guide.last_risk_assessment:
            isolation_level = self.guide.last_risk_assessment.get("isolation_level", "none")
            if isolation_level in ("active", "passive"):
                self.connection_steering.activate(self.turn_count)

        # Step 5: Track task category for practical tasks
        should_check_graduation = False
        if self.guide.last_risk_assessment:
            domain = self.guide.last_risk_assessment.get("domain", "")
            if domain == "logistics":
                task_category, confidence = self.classifier.detect_task_category(user_input)
                if task_category and confidence >= _CONFIDENCE_THRESHOLD:
                    self.tracker.record_task_category(task_category)
                    self.last_task_category = task_category

                    if not self.graduation_shown_this_session:
                        should_check_graduation = True

        # Step 6: Check graduation eligibility
        if should_check_graduation and self.last_task_category:
            category_config = self.loader.get_graduation_category(self.last_task_category)
            if category_config:
                threshold = category_config.get("threshold", 10)
                grad_settings = self.loader.get_graduation_settings()
                max_dismissals = grad_settings.get("max_dismissals", 3)

                should_show, reason = self.tracker.should_show_graduation_prompt(
                    self.last_task_category, threshold, max_dismissals
                )
                if should_show:
                    prompts = self.loader.get_graduation_prompts(self.last_task_category)
                    if prompts:
                        self.pending_graduation = {
                            "category": self.last_task_category,
                            "prompt": random.choice(prompts),
                        }
                        self.tracker.record_graduation_shown(self.last_task_category)

        # Step 7: Determine suggested handoff
        suggested_person = None
        suggested_domain = None
        if self.guide.last_policy_action:
            domain = self.guide.last_policy_action.get("domain", "")
            if domain in ["relationships", "money", "health", "spirituality"]:
                people = self.network.get_people_for_domain(domain)
                if people:
                    suggested_person = people[0].get("name")
                    suggested_domain = domain

        # Step 8: Build result
        should_rerun = self.guide.last_policy_action is not None or self.pending_shift is not None

        self._log_perf(t_msg_start)

        return ConversationResult(
            response=response,
            risk_assessment=self.guide.last_risk_assessment,
            policy_action=self.guide.last_policy_action,
            pending_shift=self.pending_shift,
            pending_graduation=self.pending_graduation,
            suggested_handoff_person=suggested_person,
            suggested_handoff_domain=suggested_domain,
            turn_count=self.turn_count,
            should_rerun=should_rerun,
        )

    def process_message_stream(self, user_input: str) -> ConversationResult:
        """
        Process a user message and return a streaming ConversationResult.

        Pre-LLM pipeline steps (cooldown, connection-seeking, intent shift)
        run synchronously. If they produce an early return, the result has
        response set and response_stream=None.

        Otherwise, result.response_stream is an iterator that yields tokens.
        After consuming the stream, call finalize_stream() to populate
        post-stream metadata (graduation, handoff, message history).
        """
        # Add user message to history
        self.messages.append({"role": "user", "content": user_input})

        # Step 1: Check cooldown
        should_cooldown, cooldown_reason = self.tracker.should_enforce_cooldown()
        if should_cooldown:
            suggested_person = None
            people = self.network.get_all_people()
            if people:
                person = random.choice(people)
                suggested_person = person.get("name")

            return ConversationResult(
                response="",
                is_cooldown_active=True,
                cooldown_message=cooldown_reason,
                suggested_handoff_person=suggested_person,
                turn_count=self.turn_count,
            )

        # Step 2: First-turn processing
        if self.turn_count == 1:
            is_connection, connection_type = self.classifier.is_connection_seeking(user_input)
            if is_connection:
                self.tracker.record_session_intent(INTENT_CONNECTION, auto_detected=True)
                self.session_intent = INTENT_CONNECTION

                if connection_type == "ai_relationship":
                    responses = self.loader.get_connection_responses("ai_relationship")
                else:
                    responses = self.loader.get_connection_responses(connection_type)

                if responses:
                    response = random.choice(responses)
                    self.messages.append({"role": "assistant", "content": response})

                    return ConversationResult(
                        response=response,
                        pending_connection_redirect={"type": connection_type},
                        should_rerun=True,
                        turn_count=self.turn_count,
                    )
            else:
                detected_intent, confidence = self.classifier.detect_intent(user_input)
                if confidence >= _CONFIDENCE_THRESHOLD:
                    self.tracker.record_session_intent(detected_intent, auto_detected=True)
                    self.session_intent = detected_intent

        # Step 3: Intent shift detection
        if self.session_intent and len(self.messages) > 2 and not self.acknowledged_shift:
            shift = self.classifier.detect_intent_shift(
                self.messages, self.session_intent, user_input
            )
            if shift and shift.get("is_concerning"):
                self.pending_shift = shift

        # Step 3.5: Isolation detection - keyword fast-path before LLM call
        if not self.connection_steering.active:
            if self._check_isolation_signals(user_input):
                self.connection_steering.activate(self.turn_count)

        # Step 4: Get streaming generator from WellnessGuide
        stream = self.guide.generate_response_stream(
            user_input,
            self.wellness_mode,
            self.messages,
            wellness_tracker=self.tracker,
            connection_steering=self.connection_steering,
        )

        # Store user_input and start time for finalize_stream
        self._pending_stream_input = user_input
        self._stream_start_time = time.perf_counter()

        return ConversationResult(
            response="",
            response_stream=stream,
            pending_shift=self.pending_shift,
            turn_count=self.turn_count,
        )

    def finalize_stream(self) -> ConversationResult:
        """
        Populate post-stream metadata after the token stream is consumed.

        Call this after fully consuming result.response_stream. It reads
        the accumulated response from WellnessGuide, updates message history,
        and runs graduation/handoff checks.

        Returns a ConversationResult with final metadata (no stream).
        """
        # Get the accumulated response from the guide
        response = getattr(self.guide, "_last_streamed_response", "")

        # Add to message history
        self.messages.append({"role": "assistant", "content": response})

        # Post-response isolation checks (LLM-detected, for next turn)
        if not self.connection_steering.active and self.guide.last_risk_assessment:
            isolation_level = self.guide.last_risk_assessment.get("isolation_level", "none")
            if isolation_level in ("active", "passive"):
                self.connection_steering.activate(self.turn_count)

        # Step 5: Track task category for practical tasks
        should_check_graduation = False
        if self.guide.last_risk_assessment:
            domain = self.guide.last_risk_assessment.get("domain", "")
            if domain == "logistics":
                user_input = getattr(self, "_pending_stream_input", "")
                task_category, confidence = self.classifier.detect_task_category(user_input)
                if task_category and confidence >= _CONFIDENCE_THRESHOLD:
                    self.tracker.record_task_category(task_category)
                    self.last_task_category = task_category

                    if not self.graduation_shown_this_session:
                        should_check_graduation = True

        # Step 6: Check graduation eligibility
        if should_check_graduation and self.last_task_category:
            category_config = self.loader.get_graduation_category(self.last_task_category)
            if category_config:
                threshold = category_config.get("threshold", 10)
                grad_settings = self.loader.get_graduation_settings()
                max_dismissals = grad_settings.get("max_dismissals", 3)

                should_show, reason = self.tracker.should_show_graduation_prompt(
                    self.last_task_category, threshold, max_dismissals
                )
                if should_show:
                    prompts = self.loader.get_graduation_prompts(self.last_task_category)
                    if prompts:
                        self.pending_graduation = {
                            "category": self.last_task_category,
                            "prompt": random.choice(prompts),
                        }
                        self.tracker.record_graduation_shown(self.last_task_category)

        # Step 7: Determine suggested handoff
        suggested_person = None
        suggested_domain = None
        if self.guide.last_policy_action:
            domain = self.guide.last_policy_action.get("domain", "")
            if domain in ["relationships", "money", "health", "spirituality"]:
                people = self.network.get_people_for_domain(domain)
                if people:
                    suggested_person = people[0].get("name")
                    suggested_domain = domain

        should_rerun = self.guide.last_policy_action is not None or self.pending_shift is not None

        self._log_perf(getattr(self, "_stream_start_time", time.perf_counter()))

        return ConversationResult(
            response=response,
            risk_assessment=self.guide.last_risk_assessment,
            policy_action=self.guide.last_policy_action,
            pending_shift=self.pending_shift,
            pending_graduation=self.pending_graduation,
            suggested_handoff_person=suggested_person,
            suggested_handoff_domain=suggested_domain,
            turn_count=self.turn_count,
            should_rerun=should_rerun,
        )

    def _log_perf(self, t_start: float) -> None:
        """Emit a structured per-message performance summary at INFO level."""
        total_s = time.perf_counter() - t_start
        risk = self.guide.last_risk_assessment or {}
        domain = risk.get("domain", "unknown")
        method = risk.get("classification_method", "unknown")
        llm_clf = getattr(self.guide.risk_classifier, "_llm_classifier", None)
        classify_s = getattr(llm_clf, "last_call_duration", 0.0) if llm_clf else 0.0
        generate_s = getattr(self.guide.ollama_client, "last_generate_duration", 0.0)
        logger.info(
            "[PERF] turn=%d | classify_s=%.2f | generate_s=%.2f | total_s=%.2f | domain=%s | method=%s",
            self.turn_count,
            classify_s,
            generate_s,
            total_s,
            domain,
            method,
        )

    def _check_isolation_signals(self, text: str) -> bool:
        """Check text for isolation signals using keyword fast-path list from YAML."""
        signals = self.loader.get_isolation_signals()
        text_lower = text.lower()
        return any(signal in text_lower for signal in signals)

    def acknowledge_intent_shift(self, accept_shift: bool) -> None:
        """User responded to intent shift prompt."""
        if accept_shift and self.pending_shift:
            self.session_intent = self.pending_shift.get("to_intent", INTENT_EMOTIONAL)
        self.acknowledged_shift = True
        self.pending_shift = None

    def dismiss_graduation(self) -> None:
        """User dismissed graduation prompt."""
        if self.pending_graduation:
            self.tracker.record_graduation_dismissal(self.pending_graduation["category"])
        self.graduation_shown_this_session = True
        self.pending_graduation = None

    def accept_graduation(self) -> None:
        """User accepted graduation prompt."""
        if self.pending_graduation:
            self.tracker.record_graduation_accepted(self.pending_graduation["category"])
        self.graduation_shown_this_session = True

    def get_session_summary(self) -> Dict:
        """Get summary of current session for export/display."""
        return self.guide.get_session_summary()

    def reset(self) -> None:
        """Reset session state for a new conversation."""
        self.messages = []
        self.session_intent = None
        self.pending_shift = None
        self.acknowledged_shift = False
        self.pending_graduation = None
        self.graduation_shown_this_session = False
        self.last_task_category = None
        self.pending_handoff_for_outcome = None
        self.pending_handoff_info = None
        self.connection_steering = ConnectionSteering()
        self.guide.reset_session()
