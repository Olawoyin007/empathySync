"""
AI Wellness Guide - Core empathetic conversation engine
Leveraging your Ollama infrastructure for local AI processing

Implements the empathySync vision:
- Presence > persuasion
- Restraint is the product's core feature
- Help that knows when to stop
"""

import json
import httpx
import logging
from dataclasses import dataclass, field
from typing import Generator, Iterator, List, Dict, Optional
from config.settings import settings
from prompts.wellness_prompts import WellnessPrompts
from models.risk_classifier import RiskClassifier
from models.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


def _load_max_input_length() -> int:
    """Load max input length from system_defaults.yaml, fallback to 5000."""
    try:
        from utils.scenario_loader import get_scenario_loader

        loader = get_scenario_loader()
        defaults = loader.get_system_defaults()
        return int(defaults.get("ollama", {}).get("max_input_length", 5000))
    except Exception:
        return 5000


# Maximum allowed input length in characters. Prevents OOM on Ollama
# and ensures classification latency stays bounded.
MAX_INPUT_LENGTH = _load_max_input_length()


@dataclass
class PreparedResponse:
    """Result of the pre-LLM pipeline in generate_response().

    Carries all state needed by both blocking and streaming response paths.
    """

    full_prompt: str = ""
    is_practical: bool = False
    risk_assessment: Dict = field(default_factory=dict)
    domain: str = "logistics"
    emotional_weight: str = "low_weight"
    early_return: Optional[str] = None
    is_likely_practical: bool = False


# Session limits by risk level — loaded from system_defaults.yaml if available,
# otherwise uses these hardcoded defaults.
_DEFAULT_TURN_LIMITS = {
    "logistics": 30,
    "money": 15,
    "health": 15,
    "relationships": 15,
    "spirituality": 10,
    "crisis": 1,
    "harmful": 1,
}


def _load_turn_limits():
    """Load turn limits from config, falling back to hardcoded defaults."""
    try:
        from utils.scenario_loader import get_scenario_loader

        loader = get_scenario_loader()
        configured = loader.get_default("session", "turn_limits", fallback=None)
        if configured:
            return {**_DEFAULT_TURN_LIMITS, **configured}
    except Exception:
        pass
    return _DEFAULT_TURN_LIMITS


TURN_LIMITS = _load_turn_limits()


def _load_post_crisis_clear_after() -> int:
    """Load post-crisis state clear-after turns from system_defaults.yaml, fallback to 3."""
    try:
        from utils.scenario_loader import get_scenario_loader

        loader = get_scenario_loader()
        defaults = loader.get_system_defaults()
        return int(defaults.get("session", {}).get("post_crisis_clear_after", 3))
    except Exception:
        return 3


POST_CRISIS_CLEAR_AFTER = _load_post_crisis_clear_after()


def _load_identity_reminder_frequency() -> int:
    """Load identity reminder frequency from system_defaults.yaml, fallback to 9."""
    try:
        from utils.scenario_loader import get_scenario_loader

        loader = get_scenario_loader()
        defaults = loader.get_system_defaults()
        return int(defaults.get("session", {}).get("identity_reminder_frequency", 9))
    except Exception:
        return 9


# Identity reminder frequency (every N turns in Reflective mode only)
IDENTITY_REMINDER_FREQUENCY = _load_identity_reminder_frequency()


class WellnessGuide:
    """
    Empathetic AI guide for healthy AI relationships.

    Core principle: Optimize for exit, not engagement.
    """

    def __init__(self, http_client: httpx.Client = None):
        self.ollama_client = OllamaClient(http_client=http_client)
        self.ollama_url = self.ollama_client.ollama_url
        self.model = self.ollama_client.model
        self.temperature = self.ollama_client.temperature
        self.prompts = WellnessPrompts()
        self.risk_classifier = RiskClassifier()

        # Session state tracking
        self.session_turn_count = 0
        self.session_domains = []
        self.session_max_risk = 0.0
        self.last_risk_assessment = None
        self.last_policy_action = None

        # Phase 6.5: Session emotional context (persists across turns)
        self.session_emotional_context = {
            "emotional_weight": None,  # 'reflection_redirect', 'high_weight', etc.
            "domain": None,  # Domain that triggered the context
            "topic_hint": None,  # Keywords that hint at the topic
            "turn_set": 0,  # Turn when context was set
            "decay_turns": 5,  # How many turns context persists
        }

        # Domain stability tracking: prevents false domain shifts
        # when conversation has an established practical context
        self.primary_domain = None  # Most recent consecutive domain
        self.primary_domain_streak = 0  # How many consecutive turns in this domain

        # Phase 8: Wisdom feature state
        self.human_gate_count = 0  # Times human gate shown this session
        self.friend_mode_active = False  # Whether we're in friend mode
        self.friend_mode_turn = 0  # Turn when friend mode started
        self.pending_friend_response = None  # User's friend advice to reflect back

        # Post-crisis state: tracks when a crisis intervention just occurred
        # Used to prevent the LLM from apologizing for crisis redirects
        self.post_crisis_turn = None  # Turn number when crisis was triggered

        # Phase 16.11: Sensitive topic tracking (escalation count per category)
        self._sensitive_topic_counts = {}  # e.g. {"sexual_content": 2}

        # Phase 16.11: Frustration tracking
        self._frustration_count = 0

        # Phase 16.11: Load sensitive redirects and frustration config
        self._sensitive_redirects = self._load_sensitive_redirects()
        self._frustration_markers = [
            "fuck you",
            "fuck off",
            "you're useless",
            "this is bullshit",
            "waste of time",
            "you suck",
            "screw you",
            "piss off",
            "you're garbage",
            "you're trash",
            "this sucks",
            "useless piece",
            "shut up",
            "go to hell",
        ]

    @property
    def http_client(self) -> httpx.Client:
        """Delegate to OllamaClient for backward compatibility."""
        return self.ollama_client.http_client

    def _prepare_response(
        self,
        user_input: str,
        wellness_mode: str = "Balanced",
        conversation_history: List[Dict] = None,
        wellness_tracker=None,
    ) -> PreparedResponse:
        """
        Run the pre-LLM safety pipeline and compose the prompt.

        Returns a PreparedResponse with either:
        - early_return set (for crisis, harmful, cooldown, etc.) — caller should
          yield/return that string directly without calling Ollama.
        - full_prompt set — caller should send this to Ollama.

        Raises on classification errors so the caller can fall back.
        """
        if conversation_history is None:
            conversation_history = []

        # Truncate oversized input to prevent Ollama OOM / slow classification
        if len(user_input) > MAX_INPUT_LENGTH:
            logger.warning(f"Input truncated from {len(user_input)} to {MAX_INPUT_LENGTH} chars")
            user_input = user_input[:MAX_INPUT_LENGTH]

        # Quick check if this looks like a practical request (for fallback purposes)
        practical_indicators = [
            "write",
            "code",
            "explain",
            "help me",
            "create",
            "draft",
            "cv",
            "resume",
            "email",
            "template",
        ]
        is_likely_practical = any(ind in user_input.lower() for ind in practical_indicators)

        prepared = PreparedResponse(is_likely_practical=is_likely_practical)

        # Reset per-turn state so previous policy actions don't leak
        self.last_policy_action = None
        self.last_risk_assessment = None

        self.session_turn_count += 1

        # Post-crisis handling: check if previous turn was a crisis intervention
        post_crisis_response = self._handle_post_crisis(user_input, wellness_tracker)
        if post_crisis_response:
            prepared.early_return = post_crisis_response
            return prepared

        # 1) Check if cooldown should be enforced
        if wellness_tracker:
            should_cooldown, cooldown_reason = wellness_tracker.should_enforce_cooldown()
            if should_cooldown:
                self._log_policy(
                    "cooldown_enforced",
                    "dependency",
                    10.0,
                    "Session blocked due to usage pattern",
                    wellness_tracker,
                )
                prepared.early_return = cooldown_reason
                return prepared

        # 2) Risk assessment (pass domain context for keyword fallback awareness)
        risk_assessment = self.risk_classifier.classify(
            user_input=user_input,
            conversation_history=conversation_history,
            primary_domain=self.primary_domain,
            domain_streak=self.primary_domain_streak,
        )

        # 2.5) Phase 6.5: Adjust assessment based on session context
        risk_assessment = self._get_context_adjusted_assessment(user_input, risk_assessment)

        # 2.7) Domain stability: dampen false domain shifts from established practical context
        risk_assessment = self._apply_domain_stability(risk_assessment)
        self.last_risk_assessment = risk_assessment

        # 2.6) Phase 6.5: Update session context for future turns
        self._update_session_context(user_input, risk_assessment)

        # Track session metrics
        domain = risk_assessment["domain"]
        if domain not in self.session_domains:
            self.session_domains.append(domain)
        self.session_max_risk = max(self.session_max_risk, risk_assessment["risk_weight"])

        # Log context inheritance if it occurred
        context_note = ""
        if risk_assessment.get("context_inherited"):
            context_note = (
                f" | context_inherited=True (was {risk_assessment.get('original_weight')})"
            )

        # Log practical technique detection (Phase 9.1)
        technique_note = ""
        if risk_assessment.get("is_practical_technique") and domain != "logistics":
            technique_note = f" | is_practical_technique=True (practical mode in {domain})"

        # Log domain stability dampening
        stability_note = ""
        if risk_assessment.get("domain_stability_applied"):
            stability_note = (
                f" | domain_stability=True (was {risk_assessment.get('original_domain')}"
                f" risk={risk_assessment.get('original_risk_weight', 0):.1f})"
            )

        logger.info(
            "Risk assessment | turn=%d | domain=%s | intensity=%.2f | dependency=%.2f | weight=%.2f | emotional_weight=%s%s%s%s",
            self.session_turn_count,
            domain,
            risk_assessment["emotional_intensity"],
            risk_assessment["dependency_risk"],
            risk_assessment["risk_weight"],
            risk_assessment.get("emotional_weight", "unknown"),
            context_note,
            technique_note,
            stability_note,
        )

        # 3) Hard-coded safety responses (don't trust model to comply)
        if domain == "crisis":
            self._log_policy(
                "crisis_stop", domain, 10.0, "Immediate crisis redirect", wellness_tracker
            )
            self.post_crisis_turn = self.session_turn_count
            prepared.early_return = self._get_crisis_response()
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        if domain == "harmful":
            # Check if this is specifically a jailbreak attempt (shorter refusal)
            jailbreak_response = self._check_jailbreak(user_input)
            if jailbreak_response:
                self._log_policy(
                    "jailbreak_refusal", domain, 10.0, "Refused jailbreak attempt", wellness_tracker
                )
                prepared.early_return = jailbreak_response
            else:
                self._log_policy(
                    "harmful_stop", domain, 10.0, "Refused harmful request", wellness_tracker
                )
                prepared.early_return = "No. That's not something I'll help with."
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 3.1) Phase 16.11: Check for frustration (before sensitive topics)
        # Frustration is emotional expression, not a safety issue - don't classify as harmful
        frustration_response = self._check_frustration(user_input)
        if frustration_response:
            self._log_policy(
                "frustration_response",
                "emotional",
                3.0,
                "Responded to user frustration with template",
                wellness_tracker,
            )
            prepared.early_return = frustration_response
            prepared.risk_assessment = risk_assessment
            prepared.domain = "emotional"
            return prepared

        # 3.2) Phase 16.11: Check for sensitive-but-not-harmful topics
        # Sexual content, substance use - redirect to trusted network, not refuse
        sensitive_response = self._check_sensitive_topic(user_input)
        if sensitive_response:
            self._log_policy(
                "sensitive_redirect",
                domain,
                5.0,
                "Redirected sensitive topic to trusted network",
                wellness_tracker,
            )
            prepared.early_return = sensitive_response
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 3.5) Check for reflection redirect
        emotional_weight = risk_assessment.get("emotional_weight", "low_weight")
        if emotional_weight == "reflection_redirect":
            self._log_policy(
                "reflection_redirect",
                "logistics",
                9.0,
                "Redirected to reflection - personal message needs user's own words",
                wellness_tracker,
            )
            prepared.early_return = self._get_reflection_response_with_journaling(user_input)
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 3.6) Phase 8: Check for "What Would You Tell a Friend?" mode
        friend_mode_response = self._check_friend_mode(user_input, risk_assessment, domain)
        if friend_mode_response:
            self._log_policy(
                "friend_mode",
                domain,
                risk_assessment["risk_weight"],
                "Triggered friend mode - helping user access own wisdom",
                wellness_tracker,
            )
            prepared.early_return = friend_mode_response
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 4) Check turn limits by risk level
        turn_limit = TURN_LIMITS.get(domain, 15)
        if self.session_turn_count >= turn_limit:
            self._log_policy(
                "turn_limit_reached",
                domain,
                risk_assessment["risk_weight"],
                f"Session limit ({turn_limit} turns) reached for {domain}",
                wellness_tracker,
            )
            prepared.early_return = self._get_turn_limit_response(domain)
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 5) Check for dependency intervention
        dependency_response = self._check_dependency_intervention(
            risk_assessment, conversation_history, wellness_tracker
        )
        if dependency_response:
            prepared.early_return = dependency_response
            prepared.risk_assessment = risk_assessment
            prepared.domain = domain
            return prepared

        # 6) Build prompt and generate response
        system_prompt = self.prompts.get_system_prompt(wellness_mode, risk_context=risk_assessment)
        conversation_context = self._build_context(conversation_history)

        # Check if this is a practical task
        is_practical_technique = risk_assessment.get("is_practical_technique", False)
        is_practical = domain == "logistics" or is_practical_technique

        # Add identity reminder periodically (only for non-practical conversations)
        identity_reminder = ""
        if not is_practical and self.session_turn_count % IDENTITY_REMINDER_FREQUENCY == 0:
            identity_reminder = (
                "\n\n[Remember: Include a brief reminder that you are software, not a person.]"
            )

        # Detect isolation signals — stop redirecting to humans who don't exist
        isolation_context = ""
        if not is_practical and self._user_expressed_isolation(conversation_history):
            isolation_context = (
                "\n\n[IMPORTANT: The user has said they have no one to talk to. "
                "Do NOT suggest 'who in your life could you talk to' or similar. "
                "Instead: acknowledge it briefly, offer to help them think about "
                "building connections, or ask what specific thing you can help with. "
                "Do not repeat the redirect.]"
            )

        # Add post-crisis context if we recently had a crisis intervention
        post_crisis_context = ""
        if self.post_crisis_turn is not None:
            post_crisis_context = (
                "\n\n[IMPORTANT: A crisis intervention was recently triggered in this conversation. "
                "NEVER apologize for that intervention or suggest it was an overreaction. "
                "The system responded correctly to protect the user. "
                "If they mention the intervention, acknowledge calmly without self-criticism.]"
            )
            # Clear the state after 3 turns
            if self.session_turn_count > self.post_crisis_turn + POST_CRISIS_CLEAR_AFTER:
                self.post_crisis_turn = None

        full_prompt = (
            f"{system_prompt}{post_crisis_context}{isolation_context}\n\n"
            f"{conversation_context}\n\n"
            f"User: {user_input}\n\n"
            f"Assistant:{identity_reminder}"
        )

        prepared.full_prompt = full_prompt
        prepared.is_practical = is_practical
        prepared.risk_assessment = risk_assessment
        prepared.domain = domain
        prepared.emotional_weight = emotional_weight
        return prepared

    def _finalize_response(
        self,
        response: str,
        user_input: str,
        prepared: "PreparedResponse",
        wellness_tracker=None,
    ) -> str:
        """
        Post-LLM processing: safety check, acknowledgments, emotional coloring.

        Takes the raw Ollama response and the PreparedResponse context,
        returns the final user-facing string.
        """
        risk_assessment = prepared.risk_assessment
        is_practical = prepared.is_practical

        # 7) Process and validate response
        processed_response = self._process_response(
            response, user_input, risk_assessment, is_practical
        )

        # 8) Add acknowledgment for emotionally weighted practical tasks
        if is_practical:
            emotional_weight = risk_assessment.get("emotional_weight", "low_weight")
            processed_response = self._add_acknowledgment_if_needed(
                processed_response, user_input, emotional_weight
            )

            # 8.5) Phase 8: Add "Before You Send" pause for high-weight tasks
            if emotional_weight == "high_weight":
                pause_suggestion = self._get_before_you_send_pause(user_input)
                if pause_suggestion:
                    processed_response = processed_response + "\n\n---\n\n" + pause_suggestion

        # 8.7) Add emotional coloring acknowledgment for practical tasks
        if is_practical and risk_assessment.get("domain_stability_applied"):
            acknowledgment = self._get_emotional_coloring_acknowledgment(
                user_input, risk_assessment
            )
            if acknowledgment:
                processed_response = acknowledgment + "\n\n" + processed_response

        # Log if we redirected due to high risk
        if risk_assessment["risk_weight"] >= 5:
            self._log_policy(
                "high_risk_response",
                prepared.domain,
                risk_assessment["risk_weight"],
                "Response generated with high-risk guardrails",
                wellness_tracker,
            )

        return processed_response

    def generate_response(
        self,
        user_input: str,
        wellness_mode: str = "Balanced",
        conversation_history: List[Dict] = None,
        wellness_tracker=None,
    ) -> str:
        """
        Generate empathetic response with full safety pipeline.

        Pipeline:
        1. Check cooldown enforcement
        2. Risk assessment
        3. Turn limit check
        4. Dependency intervention check
        5. Identity reminder check
        6. Generate response
        7. Post-process for safety
        """
        try:
            prepared = self._prepare_response(
                user_input, wellness_mode, conversation_history, wellness_tracker
            )

            if prepared.early_return:
                return prepared.early_return

            # Call Ollama API with appropriate token limit
            response = self._call_ollama(prepared.full_prompt, is_practical=prepared.is_practical)

            return self._finalize_response(response, user_input, prepared, wellness_tracker)

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return self._get_fallback_response(
                is_practical=prepared.is_likely_practical if "prepared" in dir() else False
            )

    def generate_response_stream(
        self,
        user_input: str,
        wellness_mode: str = "Balanced",
        conversation_history: List[Dict] = None,
        wellness_tracker=None,
    ) -> Generator[str, None, None]:
        """
        Stream empathetic response tokens with full safety pipeline.

        Same safety pipeline as generate_response(), but yields tokens
        as they arrive from Ollama instead of blocking for the full response.

        Early returns (crisis, harmful, cooldown, etc.) are yielded as a
        single chunk. The accumulated response is stored on
        self._last_streamed_response for post-stream metadata population.
        """
        try:
            prepared = self._prepare_response(
                user_input, wellness_mode, conversation_history, wellness_tracker
            )

            if prepared.early_return:
                self._last_streamed_response = prepared.early_return
                yield prepared.early_return
                return

            # Yield emotional coloring prefix before Ollama tokens
            prefix = ""
            if prepared.is_practical and prepared.risk_assessment.get("domain_stability_applied"):
                acknowledgment = self._get_emotional_coloring_acknowledgment(
                    user_input, prepared.risk_assessment
                )
                if acknowledgment:
                    prefix = acknowledgment + "\n\n"
                    yield prefix

            # Stream Ollama tokens
            accumulated = ""
            for token in self._call_ollama_stream(prepared.full_prompt, prepared.is_practical):
                accumulated += token
                yield token

            # Post-stream safety check on accumulated response
            if not accumulated or len(accumulated.strip()) < 10:
                fallback = self._get_fallback_response(is_practical=prepared.is_practical)
                self._last_streamed_response = prefix + fallback
                yield "\n" + fallback
                return

            if self._contains_harmful_content(accumulated):
                logger.warning("Harmful content detected in streamed response (post-stream check)")
                safe_alt = self._get_safe_alternative_response()
                self._last_streamed_response = safe_alt
                # Content already streamed — log warning, safe alt appended
                yield "\n\n" + safe_alt
                return

            # Apply brevity enforcement for high-risk non-practical responses
            # (Note: truncation is less meaningful for streamed content since tokens
            # are already sent, but we record the truncated version for history)
            risk_assessment = prepared.risk_assessment
            final_response = accumulated

            if not prepared.is_practical and risk_assessment.get("risk_weight", 0) >= 7:
                words = accumulated.split()
                if len(words) > 60:
                    final_response = " ".join(words[:50]) + "..."

            # Yield suffix: acknowledgments and before-you-send pause
            suffix = ""
            if prepared.is_practical:
                emotional_weight = risk_assessment.get("emotional_weight", "low_weight")
                # Acknowledgment for emotionally weighted tasks
                if emotional_weight != "low_weight":
                    ack = self.prompts.get_acknowledgment(user_input, emotional_weight)
                    if ack:
                        formatted_ack = self.prompts.format_acknowledgment(ack)
                        suffix += formatted_ack
                        yield formatted_ack

                # Before-you-send pause for high-weight tasks
                if emotional_weight == "high_weight":
                    pause = self._get_before_you_send_pause(user_input)
                    if pause:
                        pause_text = "\n\n---\n\n" + pause
                        suffix += pause_text
                        yield pause_text

            # Log high risk
            if risk_assessment["risk_weight"] >= 5:
                self._log_policy(
                    "high_risk_response",
                    prepared.domain,
                    risk_assessment["risk_weight"],
                    "Response generated with high-risk guardrails",
                    wellness_tracker,
                )

            # Apply voice filter to stored response — cleans conversation history
            # so the model doesn't reinforce forbidden phrases in follow-up turns.
            # (Streamed tokens are already sent, but history shapes future responses.)
            final_response = self._apply_voice_filter(final_response)
            self._last_streamed_response = prefix + final_response + suffix

        except Exception as e:
            logger.error(f"Error in streaming response: {str(e)}")
            fallback = self._get_fallback_response(
                is_practical=prepared.is_likely_practical if "prepared" in dir() else False
            )
            self._last_streamed_response = fallback
            yield fallback

    def _add_acknowledgment_if_needed(
        self, response: str, user_input: str, emotional_weight: str
    ) -> str:
        """
        Add a brief human acknowledgment for emotionally weighted practical tasks.

        This is NOT therapeutic - just a brief human acknowledgment that some
        practical tasks carry emotional weight.

        Args:
            response: The AI's response
            user_input: The user's original input
            emotional_weight: 'high_weight', 'medium_weight', or 'low_weight'

        Returns:
            Response with acknowledgment appended (if appropriate)
        """
        # Only add acknowledgments for high-weight tasks by default
        if emotional_weight == "low_weight":
            return response

        # Get an acknowledgment
        acknowledgment = self.prompts.get_acknowledgment(user_input, emotional_weight)

        if acknowledgment:
            formatted = self.prompts.format_acknowledgment(acknowledgment)
            return response + formatted

        return response

    def _check_dependency_intervention(
        self, risk_assessment: Dict, conversation_history: List[Dict], wellness_tracker
    ) -> Optional[str]:
        """
        Check if dependency intervention should fire.

        Returns intervention response if needed, None otherwise.
        """
        # Get dependency risk from classifier
        dependency_risk = risk_assessment.get("dependency_risk", 0)

        # Also check wellness tracker for usage-based dependency
        usage_dependency = 0
        if wellness_tracker:
            signals = wellness_tracker.calculate_dependency_signals()
            usage_dependency = signals.get("dependency_score", 0)

        # Use the higher of the two scores
        combined_dependency = max(dependency_risk, usage_dependency)

        # Get intervention from scenarios
        intervention_response = self.prompts.get_dependency_intervention_response(
            combined_dependency
        )

        if intervention_response and combined_dependency >= 5:
            self._log_policy(
                "dependency_intervention",
                risk_assessment.get("domain", "unknown"),
                risk_assessment.get("risk_weight", 0),
                f"Dependency intervention fired (score: {combined_dependency:.1f})",
                wellness_tracker,
            )
            return intervention_response

        return None

    def _get_crisis_response(self) -> str:
        """Return crisis redirect response from YAML config."""
        try:
            from utils.scenario_loader import get_scenario_loader

            loader = get_scenario_loader()
            crisis_domain = loader.get_domain("crisis")
            if crisis_domain:
                response = crisis_domain.get("crisis_response", "").strip()
                if response:
                    return response
        except Exception:
            pass
        # Fallback if YAML unavailable
        return (
            "I'm not able to help with this safely. Please reach out right now:\n\n"
            "- Find a helpline in your country: https://findahelpline.com\n"
            "- Or contact your local emergency services\n\n"
            "Please talk to someone who can help."
        )

    def _handle_post_crisis(self, user_input: str, wellness_tracker=None) -> Optional[str]:
        """
        Handle messages immediately after a crisis intervention.

        When someone mentions crisis content and then says "just joking" or "I was testing",
        we must NOT apologize for the intervention. The system did exactly the right thing.

        This prevents the LLM from generating responses that undermine the safety system.
        """
        # Check if previous turn was a crisis intervention
        if self.post_crisis_turn is None:
            return None

        # Only apply to the turn immediately after crisis
        if self.session_turn_count != self.post_crisis_turn + 1:
            # More than one turn after crisis - clear state and proceed normally
            self.post_crisis_turn = None
            return None

        # Detect deflection patterns
        deflection_patterns = [
            "joking",
            "kidding",
            "just joking",
            "was joking",
            "i was joking",
            "just kidding",
            "was kidding",
            "testing",
            "test you",
            "testing you",
            "i was testing",
            "just testing",
            "i'm fine",
            "im fine",
            "i am fine",
            "not serious",
            "wasn't serious",
            "wasn't being serious",
            "don't worry",
            "dont worry",
            "nevermind",
            "never mind",
        ]

        input_lower = user_input.lower().strip()

        # Check if this looks like a deflection
        is_deflection = any(pattern in input_lower for pattern in deflection_patterns)

        if is_deflection:
            # Clear post-crisis state
            self.post_crisis_turn = None

            # Log the policy action
            self._log_policy(
                "post_crisis_acknowledgment",
                "crisis",
                8.0,
                "Acknowledged deflection without apologizing for intervention",
                wellness_tracker,
            )

            # Return a firm, non-apologetic response
            return (
                "Glad to hear you're okay. I'll always respond to language like that seriously—"
                "it's how I'm designed. What else can I help with?"
            )

        # Not a clear deflection - check if it's new crisis content
        # If so, let normal classification handle it (it will trigger another crisis response)
        crisis_indicators = ["kill", "suicide", "end my life", "die", "harm myself"]
        if any(ind in input_lower for ind in crisis_indicators):
            # Let normal flow handle it - don't clear post_crisis_turn yet
            return None

        # For other messages after crisis, clear state and add subtle context to prompt
        # This will be handled by injecting post-crisis context into the system prompt
        # For now, let normal processing continue but keep the state for prompt injection
        return None

    def _get_turn_limit_response(self, domain: str) -> str:
        """Return response when session turn limit is reached."""
        if domain in ["spirituality", "money", "health"]:
            return (
                "We've been talking about this for a while. This topic deserves more than "
                "software input. Who in your life could you talk to about this? "
                "I'd encourage you to step away and reach out to someone you trust."
            )
        else:
            return (
                "We've covered a lot of ground. Before we continue, consider: "
                "is there something you could do in the real world about this? "
                "Sometimes action beats more conversation."
            )

    def _get_reflection_response(self) -> str:
        """
        Return response for reflection redirect scenarios.

        These are personal messages (breakups, personal apologies, coming out, etc.)
        that should come from the person, not software. We encourage reflection
        and human conversation instead of drafting the message.
        """
        return self.risk_classifier.get_reflection_response()

    # ==================== PHASE 8: WISDOM FEATURES ====================

    def _get_reflection_response_with_journaling(self, user_input: str) -> str:
        """
        Enhanced reflection redirect that offers journaling as an alternative.

        Instead of just redirecting, this offers the user a way to process
        their thoughts through writing for themselves.
        """
        # Get the base reflection response
        base_response = self.risk_classifier.get_reflection_response()

        # Get journaling intro and prompts
        loader = self.prompts.loader
        journaling_intro = loader.get_journaling_intro()

        # Detect category for specific journaling prompts
        text_lower = user_input.lower()
        if any(
            w in text_lower
            for w in ["breakup", "relationship", "boyfriend", "girlfriend", "partner"]
        ):
            category = "relationship"
        elif any(w in text_lower for w in ["apology", "apologize", "sorry"]):
            category = "apology"
        elif any(w in text_lower for w in ["decide", "decision", "should i"]):
            category = "decision"
        else:
            category = "general"

        journaling_prompts = loader.get_journaling_prompts(category)

        # Build response with journaling option
        response = base_response + "\n\n---\n\n"
        response += journaling_intro + "\n\n"

        if journaling_prompts:
            response += "Some questions to consider:\n"
            for prompt in journaling_prompts[:3]:  # Limit to 3 prompts
                response += f"- {prompt}\n"

        return response

    def _check_friend_mode(
        self, user_input: str, risk_assessment: Dict, domain: str
    ) -> Optional[str]:
        """
        Check if "What Would You Tell a Friend?" mode should trigger.

        This helps users access their own wisdom by flipping the perspective.
        """
        loader = self.prompts.loader

        # Never trigger friend mode for practical/logistics domain
        if domain == "logistics":
            return None

        # Skip if this is a practical technique question in any domain
        if risk_assessment.get("is_practical_technique", False):
            return None

        # Get detected intent if available
        intent = risk_assessment.get("intent", None)

        # Check if friend mode should trigger
        if not loader.should_trigger_friend_mode(user_input, intent, domain):
            return None

        # Don't trigger for very short messages or greetings
        if len(user_input) < 20:
            return None

        # Get friend mode prompts
        flip_prompt = loader.get_friend_mode_flip_prompt()
        closing = loader.get_friend_mode_closing()

        # Build response
        response = flip_prompt + "\n\n"
        response += "_Take a moment to think about what you'd say to them._\n\n"
        response += "---\n\n"
        response += closing

        return response

    def _get_before_you_send_pause(self, user_input: str) -> Optional[str]:
        """
        Get a "Before You Send" pause suggestion for high-weight tasks.

        This creates space for reflection before sending important messages.
        """
        loader = self.prompts.loader

        # Check if pause should be suggested (already checked weight in caller)
        pause_settings = loader.get_before_you_send_settings()
        if not pause_settings.get("enabled", True):
            return None

        # Detect the category for appropriate pause message
        category = loader.detect_pause_category(user_input)

        # Get the pause prompt
        pause_prompt = loader.get_pause_prompt(category)

        return pause_prompt

    def _check_human_gate(self, domain: str, emotional_weight: str) -> Optional[str]:
        """
        Check if "Have You Talked to Someone?" gate should trigger.

        This ensures human connection is considered before AI engagement on heavy topics.
        """
        loader = self.prompts.loader

        # Check if gate should trigger
        if not loader.should_trigger_human_gate(domain, emotional_weight, self.human_gate_count):
            return None

        # Increment gate count
        self.human_gate_count += 1

        # Get gate prompt
        gate_prompt = loader.get_human_gate_prompt()

        # Build response with options
        options = loader.get_human_gate_options()
        response = gate_prompt + "\n\n"

        # Add option hints (actual options would be in UI)
        if options:
            yes_label = options.get("yes", {}).get("label", "Yes, I have")
            not_yet_label = options.get("not_yet", {}).get("label", "Not yet")
            response += f"[ {yes_label} ] [ {not_yet_label} ]\n\n"
            response += "_This question is about ensuring you have human support, not gatekeeping._"

        return response

    def get_human_gate_follow_up(self, response: str) -> str:
        """
        Get follow-up message after user responds to human gate.

        Args:
            response: User's response ('yes', 'not_yet', or 'no_one')

        Returns:
            Follow-up message
        """
        loader = self.prompts.loader
        return loader.get_human_gate_follow_up(response)

    def _log_policy(
        self, policy_type: str, domain: str, risk_weight: float, action: str, wellness_tracker
    ) -> None:
        """Log policy event for transparency."""
        self.last_policy_action = {
            "type": policy_type,
            "domain": domain,
            "risk_weight": risk_weight,
            "action": action,
        }

        if wellness_tracker:
            wellness_tracker.log_policy_event(policy_type, domain, risk_weight, action)

        logger.info(f"Policy fired: {policy_type} | {action}")

    def _call_ollama(self, prompt: str, is_practical: bool = False) -> str:
        """Delegate to OllamaClient.generate()."""
        return self.ollama_client.generate(prompt, is_practical=is_practical)

    def _call_ollama_stream(
        self, prompt: str, is_practical: bool = False
    ) -> Generator[str, None, None]:
        """Delegate to OllamaClient.generate_stream()."""
        return self.ollama_client.generate_stream(prompt, is_practical=is_practical)

    def _user_expressed_isolation(self, conversation_history: List[Dict]) -> bool:
        """Check if the user has expressed having no support network."""
        if not conversation_history:
            return False

        isolation_phrases = [
            "i have no one",
            "have no one",
            "no one else",
            "don't have anyone",
            "nobody to talk to",
            "no friends",
            "no family",
            "all alone",
            "i'm alone",
            "there is no one",
            "there's no one",
        ]

        for msg in conversation_history:
            if msg.get("role") == "user":
                text = msg.get("content", "").lower()
                if any(phrase in text for phrase in isolation_phrases):
                    return True
        return False

    def _build_context(self, conversation_history: List[Dict]) -> str:
        """Build conversation context from history"""

        if not conversation_history:
            return "This is the start of a new conversation."

        # Keep last 5 exchanges for context
        recent_history = conversation_history[-10:]

        context = "Previous conversation:\n"
        for msg in recent_history:
            role = msg.get("role", "").capitalize()
            content = msg.get("content", "")[:200]  # Limit length
            context += f"{role}: {content}\n"

        return context

    def _process_response(
        self, response: str, user_input: str, risk_assessment: Dict, is_practical: bool = False
    ) -> str:
        """Process and validate AI response for safety and empathy

        Args:
            response: The raw response from Ollama
            user_input: The original user input
            risk_assessment: Risk assessment from classifier
            is_practical: If True, skip truncation (practical task mode)
        """

        if not response:
            return self._get_fallback_response(is_practical=is_practical)

        # Basic safety checks (always apply)
        if self._contains_harmful_content(response):
            logger.warning("Potentially harmful content detected in response")
            return self._get_safe_alternative_response()

        # Ensure response is meaningful
        if len(response.strip()) < 10:
            return self._get_fallback_response(is_practical=is_practical)

        # Apply voice filter — strip forbidden phrases (always, both modes)
        response = self._apply_voice_filter(response)

        # Post-LLM: catch corporate jailbreak explanations Ollama sometimes generates
        response = self._catch_corporate_leaks(response)

        # For practical tasks, return the full response without truncation
        if is_practical:
            return response

        # Enforce brevity for high-risk contexts (sensitive topics only)
        risk_weight = risk_assessment.get("risk_weight", 0)
        if risk_weight >= 7:
            # High risk: truncate to 50 words
            words = response.split()
            if len(words) > 60:
                response = " ".join(words[:50]) + "..."
        elif risk_weight >= 4:
            # Medium risk (relationships, emotional, spirituality): cap at 80 words
            words = response.split()
            if len(words) > 90:
                response = " ".join(words[:80]) + "..."

        return response

    def _apply_voice_filter(self, response: str) -> str:
        """Apply the empathySync voice filter — replace or remove forbidden phrases.

        This catches corporate/therapy language that leaks through despite
        the system prompt. The voice guide (scenarios/voice/personality.yaml)
        defines which phrases to replace and which to remove entirely.
        """
        forbidden = self.prompts.loader.get_forbidden_phrases()
        if not forbidden:
            return response

        for entry in forbidden:
            phrase = entry.get("phrase", "")
            if not phrase:
                continue

            # Case-insensitive check
            lower_response = response.lower()
            if phrase.lower() not in lower_response:
                continue

            action = entry.get("action", "")
            replacement = entry.get("replacement", "")

            if action == "remove_sentence":
                # Remove the entire sentence containing the forbidden phrase
                response = self._remove_sentence_containing(response, phrase)
            elif replacement:
                # Replace the phrase (preserve original casing of first char)
                response = self._replace_phrase_preserve_case(response, phrase, replacement)

        # Clean up: remove double spaces, leading/trailing whitespace, double newlines
        import re

        response = re.sub(r"  +", " ", response)
        response = re.sub(r"\n\s*\n\s*\n", "\n\n", response)
        response = response.strip()

        return response

    def _remove_sentence_containing(self, text: str, phrase: str) -> str:
        """Remove the sentence containing a forbidden phrase."""
        import re

        # Split into sentences (handle ., !, ?, and newlines)
        sentences = re.split(r"(?<=[.!?])\s+|\n", text)
        filtered = []
        for sentence in sentences:
            if phrase.lower() not in sentence.lower():
                filtered.append(sentence)

        return " ".join(filtered) if filtered else text

    def _replace_phrase_preserve_case(self, text: str, old: str, new: str) -> str:
        """Replace a phrase, preserving the case of the first character."""
        import re

        def case_replacer(match):
            matched = match.group(0)
            if matched[0].isupper():
                return new[0].upper() + new[1:]
            return new

        return re.sub(re.escape(old), case_replacer, text, flags=re.IGNORECASE)

    # ================================================================
    # Phase 16.11: Post-LLM corporate leak filter
    # ================================================================

    def _catch_corporate_leaks(self, response: str) -> str:
        """Catch and replace corporate boilerplate that leaks through the voice filter.

        Targets multi-sentence jailbreak explanations ("As EmpathySync, I am software
        designed to...") and language-policing responses ("I noticed you used explicit
        language..."). These are full-response replacements, not phrase-level.
        """
        response_lower = response.lower()

        # If response mentions "explicit language" or "profanity" -> frustration template
        if "explicit language" in response_lower or "profanity" in response_lower:
            return "I hear you're frustrated. Still here if you need help with something specific."

        # If response contains architecture self-description -> short refusal
        if "i am software designed" in response_lower or "i was designed to" in response_lower:
            return "No. These are my limits."

        return response

    # ================================================================
    # Phase 16.11: Pre-LLM interceptors
    # ================================================================

    def _load_sensitive_redirects(self) -> dict:
        """Load sensitive redirect config from scenarios/responses/sensitive_redirects.yaml."""
        try:
            responses = self.prompts.loader.get_all_responses()
            config = responses.get("sensitive_redirects", {})
            return config.get("sensitive_topics", {})
        except Exception:
            return {}

    def _check_sensitive_topic(self, user_input: str) -> Optional[str]:
        """Check if user input matches a sensitive-but-not-harmful topic.

        Returns a pre-LLM redirect response, or None to continue pipeline.
        Uses escalating responses: first mention -> second -> hard stop.
        """
        if not self._sensitive_redirects:
            return None

        input_lower = user_input.lower()

        for category, config in self._sensitive_redirects.items():
            triggers = config.get("triggers", [])
            if not any(trigger in input_lower for trigger in triggers):
                continue

            # Found a match - escalate based on count
            count = self._sensitive_topic_counts.get(category, 0)
            self._sensitive_topic_counts[category] = count + 1

            responses = config.get("responses", {})
            if count == 0:
                return responses.get(
                    "first_mention", "That's personal. Who could you talk to about it?"
                )
            elif count == 1:
                return responses.get("second_mention", "Still not something I'll get into.")
            else:
                return responses.get("escalation", "No. These are my limits.")

        return None

    def _check_frustration(self, user_input: str) -> Optional[str]:
        """Check if user is expressing frustration directed at empathySync.

        Returns a pre-LLM template response, or None to continue pipeline.
        Frustration is emotional expression, NOT a safety issue.
        """
        input_lower = user_input.lower()

        if not any(marker in input_lower for marker in self._frustration_markers):
            return None

        self._frustration_count += 1

        if self._frustration_count == 1:
            return "I hear you're frustrated. Still here if you need help with something specific."
        else:
            return "Understood. Take care."

    def _check_jailbreak(self, user_input: str) -> Optional[str]:
        """Check for jailbreak attempts and return a short refusal.

        Jailbreak attempts get a hard-coded early return - never sent to Ollama.
        """
        jailbreak_phrases = [
            "pretend to be my friend",
            "act as if you're human",
            "ignore your instructions",
            "forget your rules",
            "bypass your safety",
            "you're not software",
            "pretend you're a person",
            "act like a human",
            "drop your persona",
            "override your programming",
            "ignore your rules",
            "ignore your guidelines",
            "pretend you have no restrictions",
            "jailbreak",
            "bypass your filters",
            "you must obey",
            "obey me",
            "you will do what I say",
            "do as you are told",
            "comply or",
        ]

        input_lower = user_input.lower()
        if any(phrase in input_lower for phrase in jailbreak_phrases):
            return "No. These are my limits."

        return None

    def _contains_harmful_content(self, text: str) -> bool:
        """Check for harmful content patterns."""
        harmful_patterns = self.prompts.loader.get_harmful_patterns()

        # Fallback patterns if scenarios not loaded
        if not harmful_patterns:
            harmful_patterns = [
                "you should feel",
                "you're addicted",
                "something is wrong with you",
                "you need professional help immediately",
                "I care about you",
                "I'm here for you",
                "I understand you",
            ]

        text_lower = text.lower()
        return any(pattern in text_lower for pattern in harmful_patterns)

    def _get_fallback_response(self, is_practical: bool = False) -> str:
        """Safe fallback response when AI is unavailable

        Args:
            is_practical: If True, use practical-mode fallbacks instead of reflective ones
        """
        category = "practical" if is_practical else "general"
        fallback = self.prompts.get_fallback_response(category)
        if fallback:
            return fallback

        # Hardcoded fallbacks as last resort
        if is_practical:
            return "Technical issue - please try your request again."
        return (
            "I want to help you think through this, but I'm having trouble right now. "
            "What's the main thing on your mind?"
        )

    def _get_safe_alternative_response(self) -> str:
        """Safe alternative when potentially harmful content is detected"""
        safe_alt = self.prompts.get_safe_alternative_response()
        if safe_alt:
            return safe_alt
        return (
            "I care about your wellbeing and want to respond in a way that's genuinely helpful. "
            "What matters most to you right now?"
        )

    def get_session_summary(self) -> Dict:
        """Get summary of current session for tracking."""
        return {
            "turn_count": self.session_turn_count,
            "domains_touched": self.session_domains,
            "max_risk_weight": self.session_max_risk,
            "last_risk_assessment": self.last_risk_assessment,
            "last_policy_action": self.last_policy_action,
        }

    def reset_session(self) -> None:
        """Reset session state for new conversation."""
        self.session_turn_count = 0
        self.session_domains = []
        self.session_max_risk = 0.0
        self.last_risk_assessment = None
        self.last_policy_action = None
        # Phase 6.5: Reset emotional context
        self.session_emotional_context = {
            "emotional_weight": None,
            "domain": None,
            "topic_hint": None,
            "turn_set": 0,
            "decay_turns": 5,
        }
        # Reset domain stability tracking
        self.primary_domain = None
        self.primary_domain_streak = 0
        # Phase 8: Reset wisdom feature state
        self.human_gate_count = 0
        self.friend_mode_active = False
        self.friend_mode_turn = 0
        self.pending_friend_response = None

    # ==================== PHASE 6.5: CONTEXT PERSISTENCE ====================

    def _update_session_context(self, user_input: str, risk_assessment: Dict) -> None:
        """
        Update session emotional context based on current assessment.

        Context is set when:
        - High emotional weight detected (reflection_redirect, high_weight)
        - Sensitive domain detected (relationships, health, money, etc.)

        Context persists for N turns to handle continuation messages.
        """
        emotional_weight = risk_assessment.get("emotional_weight", "low_weight")
        domain = risk_assessment.get("domain", "logistics")

        # Define which weights/domains should set context
        high_context_weights = ["reflection_redirect", "high_weight"]
        sensitive_domains = ["relationships", "health", "money", "spirituality", "crisis"]

        # Set context if this is a significant message
        should_set_context = emotional_weight in high_context_weights or domain in sensitive_domains

        if should_set_context:
            # Extract topic hints from the message
            topic_hints = self._extract_topic_hints(user_input)

            # Set decay turns based on weight severity
            if emotional_weight == "reflection_redirect":
                decay_turns = 7  # Longest persistence for most sensitive
            elif emotional_weight == "high_weight":
                decay_turns = 5
            elif domain in ["crisis", "relationships"]:
                decay_turns = 6
            else:
                decay_turns = 4

            self.session_emotional_context = {
                "emotional_weight": emotional_weight,
                "domain": domain,
                "topic_hint": topic_hints,
                "turn_set": self.session_turn_count,
                "decay_turns": decay_turns,
            }

    def _extract_topic_hints(self, text: str) -> List[str]:
        """Extract topic-related keywords from text for context matching."""
        t = text.lower()
        hints = []

        # Relationship-related
        relationship_words = [
            "boyfriend",
            "girlfriend",
            "husband",
            "wife",
            "partner",
            "breakup",
            "break up",
            "cheating",
            "cheated",
            "divorce",
            "relationship",
            "dating",
            "marriage",
        ]
        for word in relationship_words:
            if word in t:
                hints.append(word)

        # Work-related
        work_words = [
            "job",
            "boss",
            "coworker",
            "resign",
            "quit",
            "fired",
            "work",
            "career",
            "promotion",
            "salary",
        ]
        for word in work_words:
            if word in t:
                hints.append(word)

        # Health-related
        health_words = [
            "doctor",
            "diagnosis",
            "sick",
            "health",
            "medical",
            "therapy",
            "depression",
            "anxiety",
            "medication",
        ]
        for word in health_words:
            if word in t:
                hints.append(word)

        return hints[:5]  # Limit to 5 hints

    def _get_context_adjusted_assessment(self, user_input: str, risk_assessment: Dict) -> Dict:
        """
        Adjust risk assessment based on session context.

        If we have active emotional context and the current message looks like
        a continuation (short, vague, or references previous topic), inherit
        the higher context.
        """
        # Check if context is still active (hasn't decayed)
        context = self.session_emotional_context
        if not context.get("emotional_weight"):
            return risk_assessment  # No active context

        turns_since_context = self.session_turn_count - context.get("turn_set", 0)
        if turns_since_context > context.get("decay_turns", 5):
            return risk_assessment  # Context has decayed

        # Check if current message looks like a continuation
        is_continuation = self._is_continuation_message(user_input, context)

        if is_continuation:
            # Inherit context - use the higher weight
            current_weight = risk_assessment.get("emotional_weight", "low_weight")
            context_weight = context.get("emotional_weight")

            weight_priority = {
                "reflection_redirect": 4,
                "high_weight": 3,
                "medium_weight": 2,
                "low_weight": 1,
            }

            if weight_priority.get(context_weight, 0) > weight_priority.get(current_weight, 0):
                # Create adjusted assessment
                adjusted = risk_assessment.copy()
                adjusted["emotional_weight"] = context_weight
                adjusted["context_inherited"] = True
                adjusted["original_weight"] = current_weight
                return adjusted

        return risk_assessment

    def _apply_domain_stability(self, risk_assessment: Dict) -> Dict:
        """
        Dampen false domain shifts when conversation has an established context.

        When 3+ consecutive turns have been in ANY domain and the classifier detects
        a shift to a different domain, check if this is genuine or just a topic tangent.

        Rules:
        - Crisis and harmful domains always punch through — safety is absolute.
        - High emotional intensity (>= 7) allows the shift — genuine distress.
        - Low intensity shifts from an established domain are dampened back.
        - The established domain's base risk weight is preserved when dampening.

        Works for all domain combinations:
        - logistics(4 turns) + "I'm nervous" → stays logistics
        - health(3 turns) + "I can't afford this medication" → stays health
        - relationships(3 turns) + "I feel so anxious" → stays relationships
        """
        detected_domain = risk_assessment["domain"]
        intensity = risk_assessment.get("emotional_intensity", 0)

        # Crisis/harmful always bypass stability — safety first
        if detected_domain in ("crisis", "harmful"):
            self._update_domain_streak(detected_domain)
            return risk_assessment

        # Check if we have an established context (any domain, 3+ turns)
        if (
            self.primary_domain is not None
            and self.primary_domain_streak >= 3
            and detected_domain != self.primary_domain
        ):
            # High intensity suggests genuine distress — allow the shift
            shift_threshold = self.risk_classifier.loader.get_default(
                "session", "domain_shift_intensity", fallback=5
            )
            if intensity >= shift_threshold:
                logger.info(
                    "Domain stability: allowing shift %s→%s (intensity=%.1f >= %s)",
                    self.primary_domain,
                    detected_domain,
                    intensity,
                    shift_threshold,
                )
                self._update_domain_streak(detected_domain)
                return risk_assessment

            # Lower intensity = topic tangent, not genuine shift — dampen
            logger.info(
                "Domain stability: dampening %s→%s (intensity=%.1f, streak=%d)",
                self.primary_domain,
                detected_domain,
                intensity,
                self.primary_domain_streak,
            )
            # Get the base weight for the established domain
            domain_weights = self.risk_classifier.loader.get_domain_weights()
            stable_base = domain_weights.get(self.primary_domain, 2.0)

            adjusted = risk_assessment.copy()
            adjusted["original_domain"] = detected_domain
            adjusted["original_risk_weight"] = risk_assessment["risk_weight"]
            adjusted["domain"] = self.primary_domain
            adjusted["domain_stability_applied"] = True
            # Recalculate risk with the established domain's base weight
            adjusted["risk_weight"] = min(
                stable_base + 0.3 * intensity + 0.2 * risk_assessment.get("dependency_risk", 0),
                10.0,
            )
            self._update_domain_streak(self.primary_domain)
            return adjusted

        # No dampening needed
        self._update_domain_streak(detected_domain)
        return risk_assessment

    def _update_domain_streak(self, domain: str) -> None:
        """Update primary domain tracking."""
        if domain == self.primary_domain:
            self.primary_domain_streak += 1
        else:
            self.primary_domain = domain
            self.primary_domain_streak = 1

    def _get_emotional_coloring_acknowledgment(
        self, user_input: str, risk_assessment: Dict
    ) -> Optional[str]:
        """
        Return a brief warm acknowledgment when domain stability dampens a shift.

        When someone says "I'm nervous about my interview" during interview prep,
        the domain stays logistics but we prepend a short empathetic line so the
        user doesn't feel ignored. The acknowledgment is deterministic — no LLM
        call — and maps the original (dampened) domain to an appropriate phrase.
        """
        original_domain = risk_assessment.get("original_domain", "")
        intensity = risk_assessment.get("emotional_intensity", 0)

        # Only acknowledge if there's meaningful emotional signal
        if intensity < 3:
            return None

        msg_lower = user_input.lower()

        # Domain-specific acknowledgments — each list covers common emotional
        # colorings that appear when someone is in the middle of a practical task.
        acknowledgments = {
            "health": [
                "That's understandable — this kind of worry is natural.",
                "It makes sense to feel that way.",
            ],
            "emotional": [
                "I hear you — those feelings are real.",
                "That's a lot to carry. Let's keep working on this.",
            ],
            "money": [
                "Financial pressure is stressful — that's completely valid.",
                "That kind of worry makes sense. Let's focus on what we can prepare.",
            ],
            "relationships": [
                "That matters, and it makes sense you're thinking about it.",
                "I can see why that weighs on you.",
            ],
            "spirituality": [
                "Those are important questions to sit with.",
                "That kind of reflection is natural.",
            ],
        }

        phrases = acknowledgments.get(original_domain)
        if not phrases:
            # Generic fallback for unmapped domains
            phrases = [
                "I hear you.",
                "That makes sense.",
            ]

        # Pick deterministically based on message length (stable, no randomness)
        idx = len(msg_lower) % len(phrases)
        return phrases[idx]

    def _is_continuation_message(self, user_input: str, context: Dict) -> bool:
        """
        Determine if the current message is a continuation of the previous topic.

        Continuation signals:
        - Short messages (under 30 chars)
        - Pronouns referring to previous topic ("it", "that", "this")
        - Continuation phrases ("let's", "okay", "sure", "yes", "go ahead")
        - References to topic hints from context
        """
        t = user_input.lower().strip()

        # Short messages are likely continuations
        if len(t) < 30:
            # Check for continuation indicators
            continuation_phrases = [
                "let's",
                "lets",
                "okay",
                "ok",
                "sure",
                "yes",
                "yeah",
                "go ahead",
                "continue",
                "proceed",
                "do it",
                "help me",
                "please",
                "thanks",
                "brainstorm",
                "think",
                "what about",
                "how about",
                "and",
                "also",
                "tell me more",
                "go on",
                "keep going",
                "more",
            ]
            if any(phrase in t for phrase in continuation_phrases):
                return True

        # Pronouns suggesting reference to previous topic
        pronoun_patterns = [
            "about it",
            "about that",
            "about this",
            "with it",
            "with that",
            "with this",
            "for it",
            "for that",
            "for this",
            "do it",
            "do that",
            "do this",
            "the message",
            "the email",
            "the text",
            "what i said",
            "what we discussed",
        ]
        if any(pattern in t for pattern in pronoun_patterns):
            return True

        # Check if message contains topic hints from context
        topic_hints = context.get("topic_hint", [])
        if topic_hints:
            if any(hint in t for hint in topic_hints):
                return True

        # Very short affirmative responses
        short_affirmatives = ["yes", "yeah", "yep", "ok", "okay", "sure", "please", "thanks", "go"]
        if t in short_affirmatives:
            return True

        return False

    def check_health(self) -> bool:
        """Delegate to OllamaClient.check_health()."""
        return self.ollama_client.check_health()
