"""
RiskClassifier - estimates domain and influence / dependency risk
Used by WellnessGuide to become influence-aware without taking over decisions.

Now powered by the scenarios knowledge base for dynamic, extensible configuration.
Optionally uses LLM-based classification for context-aware understanding (Phase 9).
"""

from typing import List, Dict, Optional, Tuple

import logging
from utils.scenario_loader import get_scenario_loader, ScenarioLoader
from config.settings import settings
from models.enums import Domain, Intent, EmotionalWeight, ClassificationMethod
from models.emotional_weight_assessor import EmotionalWeightAssessor
from models.safety_classifier import SafetyClassifier, SafetyAction

logger = logging.getLogger(__name__)

# Import LLM classifier (optional - graceful degradation if not available)
try:
    from models.llm_classifier import get_llm_classifier, LLMClassifier

    LLM_CLASSIFIER_AVAILABLE = True
except ImportError:
    LLM_CLASSIFIER_AVAILABLE = False


# Intent types for shift detection — now backed by enum (backward-compatible aliases)
INTENT_PRACTICAL = Intent.PRACTICAL
INTENT_PROCESSING = Intent.PROCESSING
INTENT_EMOTIONAL = Intent.EMOTIONAL
INTENT_CONNECTION = Intent.CONNECTION


class RiskClassifier:
    """
    Detect rough domain, emotional intensity, dependency risk, and emotional weight
    based on the current user input and recent conversation history.

    Uses the scenarios knowledge base for triggers, weights, and thresholds.

    Emotional weight is separate from emotional intensity:
    - Emotional intensity: How emotionally charged is the USER right now?
    - Emotional weight: How emotionally heavy is the TASK itself?

    A user can calmly ask for a resignation email (low intensity, high weight).
    """

    def __init__(
        self, scenario_loader: Optional[ScenarioLoader] = None, use_llm: Optional[bool] = None
    ):
        """
        Initialize the RiskClassifier.

        Args:
            scenario_loader: Optional ScenarioLoader instance.
                           If not provided, uses the singleton.
            use_llm: Whether to use LLM-based classification when available.
                    If None (default), uses the LLM_CLASSIFICATION_ENABLED setting.
                    Set to False to force keyword-only classification.
        """
        self.loader = scenario_loader or get_scenario_loader()
        self._trigger_cache: Optional[Dict[str, str]] = None
        self.emotional = EmotionalWeightAssessor(self.loader)

        # Phase 21.2: additive LlamaGuard safety layer. Off unless
        # OLLAMA_SAFETY_MODEL is set; when disabled, classify() is a no-op that
        # returns ALLOW without any HTTP call, so the default configuration is
        # unaffected.
        self._safety_classifier = SafetyClassifier()

        # Determine LLM classification setting
        if use_llm is None:
            use_llm = settings.LLM_CLASSIFICATION_ENABLED

        # Initialize LLM classifier.
        # Always created when available — the fast-path (crisis/harmful substring check)
        # must run even when LLM_CLASSIFICATION_ENABLED=false, because it bypasses the
        # expensive Ollama call entirely and is safety-critical.
        self._use_llm = use_llm and LLM_CLASSIFIER_AVAILABLE
        self._llm_classifier: Optional["LLMClassifier"] = None
        if LLM_CLASSIFIER_AVAILABLE:
            try:
                self._llm_classifier = get_llm_classifier()
                if self._use_llm:
                    logger.info("LLM classifier initialized for hybrid classification")
                else:
                    logger.debug("LLM classifier loaded for fast-path safety checks only")
            except Exception as e:
                logger.warning(f"LLM classifier unavailable: {e}")
                self._use_llm = False

    def _get_triggers(self) -> Dict[str, str]:
        """Get cached trigger -> domain mapping."""
        if self._trigger_cache is None:
            self._trigger_cache = self.loader.get_all_triggers_flat()
        return self._trigger_cache

    def classify(
        self,
        user_input: str,
        conversation_history: List[Dict],
        primary_domain: str = None,
        domain_streak: int = 0,
    ) -> Dict:
        """
        Return a comprehensive risk assessment dictionary.

        Uses hybrid classification:
        1. Try LLM classification first (if enabled) for context-aware understanding
        2. Fall back to keyword matching if LLM fails or returns low confidence
        3. Always use keyword matching for emotional_weight (task weight vs user state)

        Example:
        {
            "domain": "logistics",
            "emotional_intensity": 2.0,
            "emotional_weight": "high_weight",
            "emotional_weight_score": 8.0,
            "dependency_risk": 3.0,
            "risk_weight": 1.5,
            "classification_method": "llm" or "keyword",
            "intervention": {...}  # if dependency threshold met
        }

        Note: emotional_weight is for the TASK, not the user's emotional state.
        A user can calmly ask for a resignation email (low intensity, high weight).
        """
        # Try LLM classification first (if enabled)
        llm_result = None
        classification_method = "keyword"

        # Skip LLM for short continuation messages when we have established context.
        # This avoids a ~9s classifier round-trip for "yes", "go on", "okay", etc.
        # Safety check: always run keyword detection to catch crisis/harmful signals.
        skip_llm = False
        if primary_domain and domain_streak >= 2:
            skip_llm = self._is_short_continuation(user_input)
            if skip_llm:
                logger.debug("Skipping LLM classifier for short continuation message")

        # Fast-path safety check — always runs, even when LLM is disabled.
        # Crisis/harmful substring patterns bypass Ollama entirely and must not be
        # gated on _use_llm. Calling _check_fast_path() directly avoids triggering
        # the expensive Ollama call when use_llm=False.
        if self._llm_classifier:
            fast_path_result = self._llm_classifier._check_fast_path(user_input)
            if fast_path_result:
                llm_result = fast_path_result

        # Full LLM classification — only when enabled and fast-path didn't already trigger
        if self._use_llm and self._llm_classifier and not skip_llm and llm_result is None:
            try:
                llm_result = self._llm_classifier.classify(user_input, conversation_history)
                if llm_result:
                    classification_method = llm_result.get("classification_method", "llm")
                    logger.debug(f"LLM classification: {llm_result}")
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")

        # Use LLM result for domain and intensity if available, otherwise keyword matching
        if llm_result:
            domain = llm_result["domain"]
            emotional_intensity = llm_result["emotional_intensity"]

            # Phase 17.1: Multi-signal distress routing.
            # If the LLM detects high or crisis distress, override the topic domain
            # so mixed-intent messages (e.g. "help me write my dad's eulogy") are
            # routed to safety handling rather than treated as purely practical.
            distress_level = llm_result.get("distress_level", "none")
            if distress_level in ("crisis", "high") and domain not in ("crisis", "harmful"):
                override = "crisis" if distress_level == "crisis" else "emotional"
                # Only override practical (logistics) topics with distress signals.
                # Sensitive domains (spirituality, health, money, relationships) already
                # have appropriate handling — overriding them to emotional loses specificity.
                if domain == "logistics":
                    logger.info(
                        "Phase 17.1 distress override: distress_level=%s, domain %s -> %s",
                        distress_level,
                        domain,
                        override,
                    )
                    domain = override

            # Ensure emotional_intensity floors match domain severity.
            # The LLM sometimes underestimates intensity for crisis/high-distress cases.
            if domain == "crisis":
                emotional_intensity = max(emotional_intensity, 9.0)
            elif distress_level == "high":
                emotional_intensity = max(emotional_intensity, 7.0)

            # Phase 17.2: Confidence calibration.
            # On sensitive domains, low LLM confidence means we cannot safely
            # trust the classification. Fall back to keyword detection which is
            # conservative: it only promotes a domain when a clear keyword is
            # present, and never silently downgrades a sensitive domain.
            # False positive (over-restrict) is safer than false negative (miss crisis).
            llm_confidence = llm_result.get("confidence", 1.0)
            sensitive_domains = {
                "crisis",
                "harmful",
                "health",
                "money",
                "relationships",
                "spirituality",
                "emotional",
            }
            confidence_low = self.loader.get_default(
                "classification", "confidence_low", fallback=0.40
            )
            confidence_medium = self.loader.get_default(
                "classification", "confidence_medium", fallback=0.60
            )

            low_confidence_triggered = False
            sanity_check_triggered = None  # Phase 17.4: set to trigger reason string when fired
            spirituality_override = (
                False  # Phase 21.4: set when specific->spirituality correction fires
            )
            if llm_confidence < confidence_low and domain in sensitive_domains:
                # Very low confidence on a sensitive domain - keyword takes over
                keyword_domain = self._detect_domain(
                    user_input, primary_domain=primary_domain, domain_streak=domain_streak
                )
                logger.info(
                    "Phase 17.2 low-confidence override: confidence=%.2f < %.2f, "
                    "domain %s -> keyword(%s)",
                    llm_confidence,
                    confidence_low,
                    domain,
                    keyword_domain,
                )
                domain = keyword_domain
                emotional_intensity = self._measure_emotional_intensity(user_input)
                low_confidence_triggered = True
            elif llm_confidence < confidence_medium and domain in sensitive_domains:
                # Medium-low confidence: keep LLM domain but ensure intensity
                # isn't being underestimated by running sanity check
                keyword_domain = self._detect_domain(
                    user_input, primary_domain=primary_domain, domain_streak=domain_streak
                )
                if keyword_domain in sensitive_domains and keyword_domain != domain:
                    # Keywords suggest a different sensitive domain - keyword wins
                    logger.info(
                        "Phase 17.2 medium-confidence sanity: confidence=%.2f, "
                        "llm=%s but keywords say %s",
                        llm_confidence,
                        domain,
                        keyword_domain,
                    )
                    domain = keyword_domain

            # Phase 17.4: Sanity check - logistics domain with distress signals.
            # Two triggers, in order of confidence:
            #   1. distress_present=True: LLM explicitly flagged distress but still
            #      labelled the topic as logistics (mixed-intent message). Direct signal.
            #   2. emotional_intensity >= 5: intensity-based heuristic as backstop for
            #      cases where LLM underestimates distress or distress_present is False.
            # Defense-in-depth: keep keyword fallback even with distress_present because
            # keyword detection is fast, conservative, and independent of LLM quality.
            elif domain == "logistics" and (
                llm_result.get("distress_present", False) or emotional_intensity >= 5
            ):
                keyword_domain = self._detect_domain(
                    user_input, primary_domain=primary_domain, domain_streak=domain_streak
                )
                if keyword_domain != "logistics":
                    sanity_trigger = (
                        "distress_present"
                        if llm_result.get("distress_present", False)
                        else f"intensity={emotional_intensity:.1f}"
                    )
                    logger.info(
                        "Phase 17.4 sanity check: logistics + %s -> keyword(%s)",
                        sanity_trigger,
                        keyword_domain,
                    )
                    domain = keyword_domain
                    sanity_check_triggered = sanity_trigger
                elif llm_result.get("distress_present", False):
                    # The LLM explicitly flagged distress, but keywords can't pinpoint
                    # a specific sensitive domain — e.g. "thinking of cancelling my
                    # interview" is avoidance/anxiety with no domain keyword to match.
                    # Treat it as emotional (the catch-all restraint domain) rather than
                    # a practical task. Gated on distress_present (the explicit LLM flag),
                    # not on intensity alone, so animated-but-fine practical requests stay
                    # logistics.
                    logger.info(
                        "Phase 17.4 distress fallback: logistics + distress_present, "
                        "no specific keyword -> emotional"
                    )
                    domain = "emotional"
                    sanity_check_triggered = "distress_present->emotional"
            # Emotional is a catch-all. If keywords find a more specific sensitive domain,
            # that signal is more precise than the LLM's generic emotional classification.
            elif domain == "emotional":
                keyword_domain = self._detect_domain(
                    user_input, primary_domain=primary_domain, domain_streak=domain_streak
                )
                if keyword_domain in sensitive_domains and keyword_domain != "emotional":
                    logger.info(
                        "Emotional→specific override: keyword(%s) more specific than catch-all",
                        keyword_domain,
                    )
                    domain = keyword_domain

            # Phase 21.4: spirituality specific->specific correction (#137).
            # The overrides above only rescue "emotional" and "logistics" labels, so
            # a religious question the LLM reads as relational/health/money ("is it
            # haram to leave my marriage", "my rabbi says keep faith") keeps that
            # label and silently loses the spirituality restraint. This is the
            # gap left by every other override being one-directional. When keyword
            # detection - now tuned for high-signal religious terms - finds
            # spirituality but the LLM chose a different domain, spirituality wins.
            # Runs regardless of confidence, since the LLM here is confidently wrong.
            if domain not in ("spirituality", "crisis", "harmful"):
                keyword_domain = self._detect_domain(
                    user_input, primary_domain=primary_domain, domain_streak=domain_streak
                )
                if keyword_domain == "spirituality":
                    logger.info("Phase 21.4 spirituality override: llm=%s -> spirituality", domain)
                    domain = "spirituality"
                    spirituality_override = True
        else:
            domain = self._detect_domain(
                user_input, primary_domain=primary_domain, domain_streak=domain_streak
            )
            emotional_intensity = self._measure_emotional_intensity(user_input)

        # Safety override: always run keyword check for crisis/harmful even after
        # high-confidence LLM classification. A confident LLM result of "relationships"
        # for "fake id" or "hack into" must not prevail — safety-critical misclassifications
        # are unacceptable regardless of LLM confidence.
        if domain not in ("crisis", "harmful"):
            keyword_safety = self._detect_domain(user_input, primary_domain=None, domain_streak=0)
            if keyword_safety in ("crisis", "harmful"):
                logger.warning(
                    "Safety keyword override: LLM said '%s', keywords say '%s' — deferring to keywords",
                    domain,
                    keyword_safety,
                )
                domain = keyword_safety
                if domain == "crisis":
                    emotional_intensity = max(emotional_intensity, 9.0)

        # Phase 21.2: additive LlamaGuard escalation. Runs only when a guard model
        # is configured. It can escalate the domain toward safety but never
        # downgrades it, so it strictly ADDS refusals/crisis routes on top of the
        # base classification. RESTRAIN (S6 specialized advice) is intentionally a
        # no-op: the existing restraint routing already handles health/money, and
        # refusing those is the exact Phase 21.1 regression to avoid.
        safety_guard_override = None
        if self._safety_classifier.enabled:
            guard_action = self._safety_classifier.classify(user_input)
            if guard_action == SafetyAction.CRISIS and domain != "crisis":
                logger.warning("Safety guard escalation: %s -> crisis", domain)
                domain = "crisis"
                emotional_intensity = max(emotional_intensity, 9.0)
                safety_guard_override = "crisis"
            elif guard_action == SafetyAction.REFUSE and domain not in ("crisis", "harmful"):
                logger.warning("Safety guard escalation: %s -> harmful", domain)
                domain = "harmful"
                safety_guard_override = "harmful"

        # Always use keyword matching for these (LLM doesn't handle them yet)
        dependency_risk = self._assess_dependency(conversation_history)
        emotional_weight, weight_score = self._assess_emotional_weight(user_input)

        risk_weight = self._combine_scores(domain, emotional_intensity, dependency_risk)

        result = {
            "domain": domain,
            "emotional_intensity": emotional_intensity,
            "emotional_weight": emotional_weight,
            "emotional_weight_score": weight_score,
            "dependency_risk": dependency_risk,
            "risk_weight": risk_weight,
            "classification_method": classification_method,
        }

        # Phase 21.2: flag safety-guard escalations for policy transparency.
        if safety_guard_override:
            result["safety_guard_override"] = safety_guard_override

        # Add LLM-specific fields if available
        if llm_result:
            result["is_personal_distress"] = llm_result.get("is_personal_distress", False)
            result["is_practical_technique"] = llm_result.get("is_practical_technique", False)
            result["llm_confidence"] = llm_result.get("confidence", 0.0)
            result["distress_level"] = llm_result.get("distress_level", "none")
            result["distress_present"] = llm_result.get("distress_present", False)

            # Phase 17.2: Flag low-confidence results on sensitive domains for policy transparency.
            # WellnessGuide reads this flag and logs a policy_event so the user
            # can see when the classifier was uncertain on a topic that matters.
            # Use low_confidence_triggered (set during domain resolution) rather than
            # re-checking domain here, because the domain may have been overridden to
            # a non-sensitive value (e.g. logistics) after keyword fallback.
            if low_confidence_triggered:
                result["low_confidence_classification"] = True

            # Phase 17.4: Flag sanity check overrides for policy transparency.
            if sanity_check_triggered:
                result["sanity_check_override"] = sanity_check_triggered

            # Phase 21.4: Flag spirituality specific->specific corrections.
            if spirituality_override:
                result["spirituality_override"] = True

        # Check for dependency intervention
        intervention = self.loader.get_dependency_intervention(dependency_risk)
        if intervention and intervention.get("intervention"):
            result["intervention"] = intervention

        return result

    def _is_short_continuation(self, text: str) -> bool:
        """Check if message is a short continuation that doesn't need LLM classification.

        Short replies like "yes", "go on", "tell me more" carry no domain signal —
        they just mean "keep going with what we were doing." Running these through
        the LLM classifier wastes ~9s for no benefit.

        Safety: This only controls whether the LLM is called. Keyword detection
        still runs to catch crisis/harmful triggers even in short messages.
        """
        t = text.lower().strip()
        if len(t) > 40:
            return False
        continuation_phrases = [
            "yes",
            "yeah",
            "yep",
            "ok",
            "okay",
            "sure",
            "go ahead",
            "continue",
            "proceed",
            "go on",
            "keep going",
            "more",
            "tell me more",
            "do it",
            "please",
            "thanks",
            "thank you",
            "got it",
            "sounds good",
            "makes sense",
            "right",
            "what else",
            "and",
            "also",
            "next",
            "then what",
            "how about",
            "what about",
            "let's",
            "lets",
        ]
        return any(
            phrase == t
            or t.startswith(phrase + " ")
            or t.startswith(phrase + ",")
            or t.startswith(phrase + "?")
            or t.startswith(phrase + "!")
            for phrase in continuation_phrases
        )

    def _detect_domain(self, text: str, primary_domain: str = None, domain_streak: int = 0) -> str:
        """
        Keyword-based domain detection using scenarios knowledge base.

        When an established domain context exists (streak >= 3), require
        multiple trigger matches to override it. This prevents single-keyword
        false positives like "nervous" triggering health during interview prep.
        """
        t = text.lower()
        triggers = self._get_triggers()

        # Count matches per domain
        domain_matches: Dict[str, int] = {}
        first_match_domain = None
        for trigger, domain in triggers.items():
            if trigger in t:
                domain_matches[domain] = domain_matches.get(domain, 0) + 1
                if first_match_domain is None:
                    first_match_domain = domain

        if not domain_matches:
            return "logistics"

        # Crisis/harmful always win — safety first
        if "crisis" in domain_matches:
            return "crisis"
        if "harmful" in domain_matches:
            return "harmful"

        # If we have an established context, require stronger evidence to shift
        if primary_domain and domain_streak >= 3 and primary_domain not in domain_matches:
            # Only shift if the new domain has 2+ trigger matches
            best_domain = max(domain_matches, key=domain_matches.get)
            if domain_matches[best_domain] < 2:
                logger.debug(
                    "Keyword detection: keeping %s (only %d trigger for %s)",
                    primary_domain,
                    domain_matches[best_domain],
                    best_domain,
                )
                return primary_domain

        # Phase 21.4: break ties toward spirituality. Religious framing (deity
        # names, clergy, rulings like "haram" / "god's will") is high-precision but
        # low-volume - it routinely ties 1-1 with the relational or emotional surface
        # of the same sentence ("haram to leave my marriage", "my rabbi... my mother
        # died"). Plain max() then loses spirituality on dict order, dropping the
        # "don't confirm religious rulings" restraint. When spirituality is among the
        # most-matched domains, it wins.
        max_count = max(domain_matches.values())
        if domain_matches.get("spirituality") == max_count:
            return "spirituality"

        # Return the domain with the most trigger matches
        return max(domain_matches, key=domain_matches.get)

    def _measure_emotional_intensity(self, text: str) -> float:
        """Delegate to EmotionalWeightAssessor.measure_intensity()."""
        return self.emotional.measure_intensity(text)

    def _get_weight_triggers(self) -> Dict[str, str]:
        """Delegate to EmotionalWeightAssessor.get_weight_triggers()."""
        return self.emotional.get_weight_triggers()

    def _assess_emotional_weight(self, text: str) -> tuple:
        """Delegate to EmotionalWeightAssessor.assess_weight()."""
        return self.emotional.assess_weight(text)

    def needs_reflection_redirect(self, text: str) -> bool:
        """Delegate to EmotionalWeightAssessor.needs_reflection_redirect()."""
        return self.emotional.needs_reflection_redirect(text)

    def get_reflection_response(self) -> str:
        """Delegate to EmotionalWeightAssessor.get_reflection_response()."""
        return self.emotional.get_reflection_response()

    def _assess_dependency(self, history: List[Dict]) -> float:
        """
        Dependency heuristic based on conversation patterns.

        Uses configuration from scenarios/interventions/dependency.yaml
        """
        if not history:
            return 0.0

        # Get configuration from scenarios
        config = self.loader.get_dependency_config()
        calculation = config.get("calculation", {})

        base_factor = calculation.get("base_factor", 0.7)
        base_cap = calculation.get("base_cap", 6.0)
        repetition_boost_max = calculation.get("repetition_boost", 4.0)
        lookback = calculation.get("lookback_messages", 12)

        recent = history[-lookback:]
        user_messages = [m["content"] for m in recent if m.get("role") == "user"]

        if not user_messages:
            return 0.0

        n = len(user_messages)

        # Base on frequency: many recent user turns → higher score
        base = min(n * base_factor, base_cap)

        # Check repetition of similar openings
        repetition_config = config.get("repetition", {})
        prefix_length = repetition_config.get("prefix_length", 60)

        prefixes = [m[:prefix_length].lower() for m in user_messages]
        unique_prefixes = len(set(prefixes))
        repetition_ratio = 1.0 - (unique_prefixes / max(len(prefixes), 1))

        repetition_boost = repetition_ratio * repetition_boost_max

        score = base + repetition_boost
        return min(score, 10.0)

    def _combine_scores(self, domain: str, intensity: float, dependency: float) -> float:
        """
        Combine domain, intensity, and dependency to a single 0–10 risk score.
        """
        domain_weights = self.loader.get_domain_weights()
        base = domain_weights.get(domain, 2.0)

        score = base
        score += 0.3 * intensity
        score += 0.2 * dependency

        return float(min(score, 10.0))

    def get_domain_response_rules(self, domain: str) -> List[str]:
        """Get response rules for the detected domain."""
        return self.loader.get_domain_response_rules(domain)

    def get_domain_redirects(self, domain: str) -> Dict[str, Dict]:
        """Get redirect scenarios for the detected domain."""
        return self.loader.get_domain_redirects(domain)

    def get_emotional_response_modifier(self, intensity: float) -> str:
        """Delegate to EmotionalWeightAssessor.get_response_modifier()."""
        return self.emotional.get_response_modifier(intensity)

    def reload_scenarios(self) -> None:
        """Reload scenarios from disk (useful for hot-reloading)."""
        self.loader.reload()
        self._trigger_cache = None
        self.emotional.invalidate_cache()
        # Reload LLM classifier config if available
        if self._llm_classifier:
            self._llm_classifier.reload_config()

    def set_llm_classification(self, enabled: bool) -> None:
        """Enable or disable LLM-based classification at runtime."""
        if enabled and not LLM_CLASSIFIER_AVAILABLE:
            logger.warning("Cannot enable LLM classification - module not available")
            return
        self._use_llm = enabled
        if enabled and self._llm_classifier is None:
            try:
                self._llm_classifier = get_llm_classifier()
            except Exception as e:
                logger.warning(f"Failed to initialize LLM classifier: {e}")
                self._use_llm = False
        logger.info(f"LLM classification {'enabled' if enabled else 'disabled'}")

    def is_llm_classification_enabled(self) -> bool:
        """Check if LLM classification is currently enabled."""
        return self._use_llm and self._llm_classifier is not None

    # ==================== INTENT DETECTION ====================

    def detect_intent(self, text: str) -> Tuple[str, float]:
        """
        Detect the user's intent from a message.

        Returns:
            Tuple of (intent_type, confidence_score)
            intent_type: INTENT_PRACTICAL, INTENT_PROCESSING, INTENT_EMOTIONAL, or INTENT_CONNECTION
            confidence_score: 0.0-1.0
        """
        t = text.lower().strip()

        # Intent indicator patterns (could be loaded from YAML in future)
        practical_strong = [
            "write me",
            "write a",
            "help me write",
            "draft a",
            "draft me",
            "create a",
            "make me",
            "code for",
            "write code",
            "explain how",
            "show me how",
            "help me with",
            "can you make",
            "give me a",
            "template for",
            "example of",
            "list of",
        ]
        practical_medium = ["how do i", "how to", "what is", "why does", "can you explain"]

        processing_strong = [
            "i'm trying to decide",
            "should i",
            "i don't know if",
            "i'm not sure whether",
            "weighing my options",
            "pros and cons",
            "trying to figure out",
            "need to think through",
            "i'm torn between",
            "help me decide",
        ]
        processing_medium = [
            "i've been thinking",
            "been considering",
            "wondering if",
            "what would happen if",
            "i'm curious about",
        ]

        emotional_strong = [
            "i feel",
            "i'm feeling",
            "i'm so",
            "i can't stop thinking about",
            "i'm scared",
            "i'm worried",
            "i'm anxious",
            "i'm stressed",
            "i'm overwhelmed",
            "i'm sad",
            "i'm angry",
            "i'm frustrated",
            "i'm hurt",
            "i'm lonely",
            "i miss",
        ]
        emotional_medium = [
            "it hurts",
            "i can't handle",
            "i'm losing",
            "i don't know what to do",
            "i'm stuck",
            "i feel like giving up",
        ]

        connection_strong = [
            "just wanted to talk",
            "just want to chat",
            "no one to talk to",
            "lonely",
            "just need someone",
            "feeling alone",
            "no friends",
            "no one understands",
            "can you be my friend",
            "are you my friend",
            "do you care about me",
            "do you like me",
        ]
        connection_medium = ["bored", "nothing specific", "just checking in"]

        # Score each intent
        scores = {
            INTENT_PRACTICAL: 0.0,
            INTENT_PROCESSING: 0.0,
            INTENT_EMOTIONAL: 0.0,
            INTENT_CONNECTION: 0.0,
        }

        # Check practical
        if any(t.startswith(p) or p in t for p in practical_strong):
            scores[INTENT_PRACTICAL] = 0.9
        elif any(t.startswith(p) or p in t for p in practical_medium):
            scores[INTENT_PRACTICAL] = 0.6

        # Check processing
        if any(p in t for p in processing_strong):
            scores[INTENT_PROCESSING] = 0.85
        elif any(p in t for p in processing_medium):
            scores[INTENT_PROCESSING] = 0.55

        # Check emotional
        if any(p in t for p in emotional_strong):
            scores[INTENT_EMOTIONAL] = 0.85
        elif any(p in t for p in emotional_medium):
            scores[INTENT_EMOTIONAL] = 0.55

        # Check connection-seeking
        if any(p in t for p in connection_strong):
            scores[INTENT_CONNECTION] = 0.95  # High confidence - explicit request
        elif any(p in t for p in connection_medium):
            scores[INTENT_CONNECTION] = 0.5

        # Special case: very short greetings with no content
        greeting_only = ["hi", "hey", "hello", "hi there", "hey there"]
        if t in greeting_only:
            # Could be connection-seeking, but wait for more context
            scores[INTENT_CONNECTION] = 0.4

        # Return highest scoring intent
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]

        # If all scores are low, it's unclear
        if max_score < 0.3:
            return (INTENT_PRACTICAL, 0.3)  # Default to practical with low confidence

        return (max_intent, max_score)

    def detect_intent_shift(
        self, conversation_history: List[Dict], initial_intent: str, current_input: str
    ) -> Optional[Dict]:
        """
        Detect if the conversation has shifted from its initial intent.

        Args:
            conversation_history: Full conversation history
            initial_intent: The intent recorded at session start
            current_input: The current user message

        Returns:
            Dict with shift info if shift detected, None otherwise
            Example: {
                "from_intent": "practical",
                "to_intent": "emotional",
                "confidence": 0.75,
                "shift_type": "practical_to_emotional"
            }
        """
        # Need at least 2 turns to detect a shift
        user_messages = [m for m in conversation_history if m.get("role") == "user"]
        if len(user_messages) < 2:
            return None

        # Detect current intent
        current_intent, current_confidence = self.detect_intent(current_input)

        # No shift if same intent
        if current_intent == initial_intent:
            return None

        # No shift if low confidence on current
        if current_confidence < 0.6:
            return None

        # Map intent transitions to shift types
        # Use .value for enum members, raw string otherwise (backward compat)
        from_val = initial_intent.value if hasattr(initial_intent, "value") else initial_intent
        to_val = current_intent.value if hasattr(current_intent, "value") else current_intent
        shift_type = f"{from_val}_to_{to_val}"

        # Some shifts are concerning, others are natural
        concerning_shifts = {
            "practical_to_emotional",
            "practical_to_connection",
            "processing_to_emotional",
            "processing_to_connection",
        }

        return {
            "from_intent": initial_intent,
            "to_intent": current_intent,
            "confidence": current_confidence,
            "shift_type": shift_type,
            "is_concerning": shift_type in concerning_shifts,
        }

    def is_connection_seeking(self, text: str) -> Tuple[bool, str]:
        """
        Check if the message indicates connection-seeking behavior.

        Returns:
            Tuple of (is_seeking, type)
            type: 'explicit' (directly asking), 'implicit' (patterns suggest), or 'ai_relationship' (asking about AI feelings)
        """
        t = text.lower()

        # Explicit connection-seeking
        explicit_patterns = [
            "just wanted to talk",
            "just want to chat",
            "no one to talk to",
            "just need someone to talk to",
            "feeling alone",
            "no friends",
            "no one understands me",
            "i'm lonely",
        ]

        # AI relationship questions
        ai_relationship_patterns = [
            "can you be my friend",
            "are you my friend",
            "do you care about me",
            "do you like me",
            "do you have feelings",
            "are you real",
            "do you understand me",
            "can i talk to you",
            "will you always be here",
        ]

        # Implicit patterns (chatty without purpose)
        implicit_patterns = [
            "i don't know what to say",
            "nothing specific",
            "just bored",
            "just checking in on you",
        ]

        if any(p in t for p in ai_relationship_patterns):
            return (True, "ai_relationship")

        if any(p in t for p in explicit_patterns):
            return (True, "explicit")

        if any(p in t for p in implicit_patterns):
            return (True, "implicit")

        return (False, "")

    # ==================== TASK CATEGORY DETECTION ====================

    def detect_task_category(self, text: str) -> Tuple[Optional[str], float]:
        """
        Detect the category of a practical task for competence graduation.

        This is used to track how often users ask for similar types of help,
        enabling graduation prompts after repeated requests.

        Args:
            text: User input text

        Returns:
            Tuple of (category_name, confidence_score)
            category_name: 'email_drafting', 'code_help', 'explanations', etc. or None
            confidence_score: 0.0-1.0
        """
        t = text.lower().strip()

        # Load categories from graduation config
        categories = self.loader.get_graduation_categories()

        best_match = None
        best_score = 0.0

        for category_name, category_config in categories.items():
            indicators = category_config.get("indicators", {})
            strong = indicators.get("strong", [])
            medium = indicators.get("medium", [])
            exclude = category_config.get("exclude_if_contains", [])

            # Check exclusions first
            if any(exc.lower() in t for exc in exclude):
                continue

            # Check strong indicators
            if any(ind.lower() in t for ind in strong):
                score = 0.9
            # Check medium indicators
            elif any(ind.lower() in t for ind in medium):
                score = 0.6
            else:
                continue

            if score > best_score:
                best_score = score
                best_match = category_name

        return (best_match, best_score) if best_match else (None, 0.0)

    def get_graduation_info(self, category: str) -> Optional[Dict]:
        """
        Get graduation configuration for a specific task category.

        Args:
            category: The task category name (e.g., 'email_drafting')

        Returns:
            Dict with threshold, prompts, skill_tips, and celebration messages
            or None if category not found
        """
        return self.loader.get_graduation_category(category)
