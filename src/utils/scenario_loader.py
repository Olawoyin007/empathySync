"""
ScenarioLoader - Loads and manages the scenarios knowledge base

This module provides access to the structured YAML-based scenarios repository,
enabling dynamic loading of domains, emotional markers, interventions, prompts,
and response templates without code changes.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from functools import lru_cache


class ScenarioLoader:
    """
    Loads and provides access to the scenarios knowledge base.

    The scenarios directory contains structured YAML files for:
    - domains/: Risk domains (money, health, relationships, etc.)
    - emotional_markers/: Intensity levels and their markers
    - interventions/: Dependency, session boundaries, graduation paths
    - prompts/: Check-ins, mindfulness, styles
    - responses/: Fallbacks, safe alternatives, base prompts
    """

    def __init__(self, scenarios_path: Optional[str] = None):
        """
        Initialize the ScenarioLoader.

        Args:
            scenarios_path: Path to the scenarios directory.
                          Defaults to project_root/scenarios/
        """
        if scenarios_path:
            self.scenarios_path = Path(scenarios_path)
        else:
            # Default to project_root/scenarios/
            project_root = Path(__file__).parent.parent.parent
            self.scenarios_path = project_root / "scenarios"

        self._cache: Dict[str, Any] = {}
        self._validate_scenarios_path()

    def _validate_scenarios_path(self) -> None:
        """Verify the scenarios directory exists."""
        if not self.scenarios_path.exists():
            raise FileNotFoundError(f"Scenarios directory not found: {self.scenarios_path}")

    def _load_yaml(self, file_path: Path) -> Dict:
        """Load a single YAML file."""
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_directory(self, subdir: str) -> Dict[str, Dict]:
        """Load all YAML files from a subdirectory."""
        cache_key = f"dir_{subdir}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        dir_path = self.scenarios_path / subdir
        if not dir_path.exists():
            return {}

        result = {}
        for yaml_file in dir_path.glob("*.yaml"):
            name = yaml_file.stem
            result[name] = self._load_yaml(yaml_file)

        self._cache[cache_key] = result
        return result

    # ==================== DOMAINS ====================

    def get_all_domains(self) -> Dict[str, Dict]:
        """Load all domain configurations."""
        return self._load_directory("domains")

    def get_domain(self, domain_name: str) -> Optional[Dict]:
        """Get a specific domain configuration."""
        domains = self.get_all_domains()
        return domains.get(domain_name)

    def get_domain_triggers(self) -> Dict[str, List[str]]:
        """Get all domain triggers as a mapping of domain -> trigger words."""
        domains = self.get_all_domains()
        return {name: config.get("triggers", []) for name, config in domains.items()}

    def get_domain_weights(self) -> Dict[str, float]:
        """Get risk weights for all domains."""
        domains = self.get_all_domains()
        return {name: config.get("risk_weight", 1.0) for name, config in domains.items()}

    def get_domain_response_rules(self, domain_name: str) -> List[str]:
        """Get response rules for a specific domain."""
        domain = self.get_domain(domain_name)
        if domain:
            return domain.get("response_rules", [])
        return []

    def get_domain_redirects(self, domain_name: str) -> Dict[str, Dict]:
        """Get redirect scenarios for a specific domain."""
        domain = self.get_domain(domain_name)
        if domain:
            return domain.get("redirects", {})
        return {}

    # ==================== EMOTIONAL MARKERS ====================

    def get_all_emotional_markers(self) -> Dict[str, Dict]:
        """Load all emotional marker configurations."""
        return self._load_directory("emotional_markers")

    def get_emotional_markers_by_level(self) -> Dict[str, List[str]]:
        """Get markers grouped by intensity level."""
        markers = self.get_all_emotional_markers()
        return {name: config.get("markers", []) for name, config in markers.items()}

    def get_emotional_score(self, level: str) -> float:
        """Get the score for an emotional intensity level."""
        markers = self.get_all_emotional_markers()
        if level in markers:
            return markers[level].get("score", 3.0)
        return 3.0

    def get_emotional_response_modifier(self, level: str) -> str:
        """Get the response modifier for an emotional intensity level."""
        markers = self.get_all_emotional_markers()
        if level in markers:
            return markers[level].get("response_modifier", "")
        return ""

    # ==================== INTERVENTIONS ====================

    def get_all_interventions(self) -> Dict[str, Dict]:
        """Load all intervention configurations."""
        return self._load_directory("interventions")

    def get_dependency_config(self) -> Dict:
        """Get dependency intervention configuration."""
        interventions = self.get_all_interventions()
        return interventions.get("dependency", {})

    def get_dependency_levels(self) -> List[Dict]:
        """Get dependency intervention levels."""
        config = self.get_dependency_config()
        return config.get("levels", [])

    def get_dependency_intervention(self, score: float) -> Optional[Dict]:
        """Get the appropriate intervention for a dependency score."""
        levels = self.get_dependency_levels()
        intervention = None
        for level in levels:
            if score >= level.get("threshold", 0):
                intervention = level
        return intervention

    def get_session_boundaries(self) -> Dict:
        """Get session boundary configuration."""
        interventions = self.get_all_interventions()
        return interventions.get("session_boundaries", {})

    def get_graduation_skills(self) -> List[Dict]:
        """Get graduation skill-building configurations."""
        interventions = self.get_all_interventions()
        graduation = interventions.get("graduation", {})
        return graduation.get("skills", [])

    # ==================== PROMPTS ====================

    def get_all_prompts(self) -> Dict[str, Dict]:
        """Load all prompt configurations."""
        return self._load_directory("prompts")

    def get_check_in_prompts(self) -> Dict[str, List[str]]:
        """Get check-in prompts by category."""
        prompts = self.get_all_prompts()
        check_ins = prompts.get("check_ins", {})
        # Return all categories except metadata
        return {k: v for k, v in check_ins.items() if isinstance(v, list)}

    def get_mindfulness_prompts(self) -> Dict[str, List[str]]:
        """Get mindfulness prompts by category."""
        prompts = self.get_all_prompts()
        mindfulness = prompts.get("mindfulness", {})
        return {k: v for k, v in mindfulness.items() if isinstance(v, list)}

    def get_human_connection_prompts(self) -> Dict:
        """Get human connection prompts and templates."""
        prompts = self.get_all_prompts()
        return prompts.get("human_connection", {})

    def get_style_config(self, style_name: str) -> Optional[Dict]:
        """Get configuration for a specific communication style."""
        prompts = self.get_all_prompts()
        styles = prompts.get("styles", {})
        return styles.get(style_name.lower())

    def get_style_modifier(self, style_name: str) -> str:
        """Get the prompt modifier for a style."""
        config = self.get_style_config(style_name)
        if config:
            return config.get("modifier", "")
        return ""

    # ==================== VOICE ====================

    def get_voice_config(self) -> Dict:
        """Get the empathySync voice/personality configuration."""
        voice_data = self._load_directory("voice")
        return voice_data.get("personality", {})

    def get_voice_prompt_addition(self) -> str:
        """Get the voice rules to inject into system prompts."""
        config = self.get_voice_config()
        return config.get("system_prompt_addition", "")

    def get_voice_principles(self) -> List[str]:
        """Get voice principles list."""
        config = self.get_voice_config()
        return config.get("principles", [])

    def get_forbidden_phrases(self) -> List[Dict]:
        """Get forbidden phrase definitions for post-filtering."""
        config = self.get_voice_config()
        return config.get("forbidden_phrases", [])

    def get_voice_tone(self, context: str) -> Dict:
        """Get tone instructions for a specific context."""
        config = self.get_voice_config()
        tones = config.get("tone", {})
        return tones.get(context, {})

    # ==================== RESPONSES ====================

    def get_all_responses(self) -> Dict[str, Dict]:
        """Load all response configurations."""
        return self._load_directory("responses")

    def get_fallback_responses(self, category: str = "general") -> List[str]:
        """Get fallback responses by category."""
        responses = self.get_all_responses()
        fallbacks = responses.get("fallbacks", {})
        return fallbacks.get(category, fallbacks.get("general", []))

    def get_safe_alternative_responses(self) -> List[str]:
        """Get safe alternative responses for harmful content."""
        responses = self.get_all_responses()
        safe_alts = responses.get("safe_alternatives", {})
        return safe_alts.get("harmful_content_detected", [])

    def get_harmful_patterns(self) -> List[str]:
        """Get patterns that indicate potentially harmful responses."""
        responses = self.get_all_responses()
        safe_alts = responses.get("safe_alternatives", {})
        return safe_alts.get("harmful_patterns", [])

    def get_base_prompt_config(self) -> Dict:
        """Get base prompt configuration."""
        responses = self.get_all_responses()
        return responses.get("base_prompt", {})

    def get_acknowledgments(self) -> Dict:
        """Get acknowledgment templates for emotionally weighted tasks."""
        responses = self.get_all_responses()
        return responses.get("acknowledgments", {})

    def get_acknowledgment_by_category(self, style: str, category: str) -> List[str]:
        """
        Get acknowledgment templates for a specific style and category.

        Args:
            style: 'warm' or 'brief'
            category: e.g., 'endings', 'apologies', 'grief', 'general'

        Returns:
            List of acknowledgment strings
        """
        acknowledgments = self.get_acknowledgments()
        style_data = acknowledgments.get(style, {})
        return style_data.get(category, style_data.get("general", []))

    def get_acknowledgment_config(self) -> Dict:
        """Get acknowledgment configuration."""
        acknowledgments = self.get_acknowledgments()
        return acknowledgments.get("config", {})

    # ==================== EMOTIONAL WEIGHT ====================

    def get_all_emotional_weights(self) -> Dict[str, Dict]:
        """Load all emotional weight configurations."""
        return self._load_directory("emotional_weight")

    def get_task_weights(self) -> Dict:
        """Get task weight configuration."""
        weights = self.get_all_emotional_weights()
        return weights.get("task_weights", {})

    def get_emotional_weight_triggers(self) -> Dict[str, List[str]]:
        """
        Get emotional weight triggers grouped by weight level.

        Returns:
            Dict with 'reflection_redirect', 'high_weight' and 'medium_weight' trigger lists
        """
        task_weights = self.get_task_weights()
        return {
            "reflection_redirect": task_weights.get("reflection_redirect", {}).get("triggers", []),
            "high_weight": task_weights.get("high_weight", {}).get("triggers", []),
            "medium_weight": task_weights.get("medium_weight", {}).get("triggers", []),
        }

    def get_reflection_redirect_config(self) -> Dict:
        """
        Get configuration for reflection redirect tasks.

        Returns:
            Dict with triggers, responses, follow_up_prompts
        """
        task_weights = self.get_task_weights()
        return task_weights.get("reflection_redirect", {})

    def get_reflection_redirect_response(self) -> str:
        """
        Get a random reflection redirect response.

        Returns:
            A response string encouraging reflection instead of drafting
        """
        import random

        config = self.get_reflection_redirect_config()
        responses = config.get("responses", [])
        if responses:
            return random.choice(responses)
        return "This message should come from you, not software. Want to talk through what you're feeling first?"

    def get_reflection_follow_up_prompts(self) -> List[str]:
        """
        Get follow-up prompts for reflection redirect.

        Returns:
            List of prompts to help user think through their message
        """
        config = self.get_reflection_redirect_config()
        return config.get("follow_up_prompts", [])

    def get_emotional_weight_score(self, level: str) -> float:
        """
        Get the weight score for an emotional weight level.

        Args:
            level: 'high_weight', 'medium_weight', or 'low_weight'

        Returns:
            Weight score (0-10)
        """
        task_weights = self.get_task_weights()
        level_config = task_weights.get(level, {})
        return level_config.get("weight_score", 2.0)

    def get_acknowledgment_style_for_weight(self, level: str) -> str:
        """
        Get the acknowledgment style for an emotional weight level.

        Args:
            level: 'high_weight', 'medium_weight', or 'low_weight'

        Returns:
            'warm', 'brief', or 'none'
        """
        task_weights = self.get_task_weights()
        level_config = task_weights.get(level, {})
        return level_config.get("acknowledgment_style", "none")

    def get_acknowledgment_category_mapping(self) -> Dict[str, str]:
        """
        Get the keyword to category mapping for acknowledgments.

        Returns:
            Dict mapping keywords to acknowledgment categories
        """
        ack_config = self.get_acknowledgment_config()
        return ack_config.get("category_matching", {})

    # ==================== INTENTS ====================

    def get_all_intents(self) -> Dict[str, Dict]:
        """Load all intent configurations."""
        return self._load_directory("intents")

    def get_session_intent_config(self) -> Dict:
        """Get session intent check-in configuration."""
        intents = self.get_all_intents()
        return intents.get("session_intents", {})

    def get_intent_check_in_config(self) -> Dict:
        """Get the check-in configuration for session start."""
        config = self.get_session_intent_config()
        return config.get("check_in", {})

    def get_intent_indicators(self) -> Dict[str, Dict[str, List[str]]]:
        """Get intent indicators for auto-detection."""
        config = self.get_session_intent_config()
        return config.get("intent_indicators", {})

    def get_intent_shift_config(self) -> Dict:
        """Get configuration for intent shift detection."""
        config = self.get_session_intent_config()
        return config.get("shift_detection", {})

    def get_connection_responses(self, response_type: str = "explicit") -> List[str]:
        """
        Get connection-seeking response templates.

        Args:
            response_type: 'explicit', 'implicit', or 'ai_relationship'

        Returns:
            List of response strings
        """
        config = self.get_session_intent_config()
        responses = config.get("connection_responses", {})
        return responses.get(response_type, [])

    # ==================== GRADUATION ====================

    def get_all_graduation_config(self) -> Dict[str, Dict]:
        """Load all graduation configurations."""
        return self._load_directory("graduation")

    def get_practical_skills_config(self) -> Dict:
        """Get practical skills graduation configuration."""
        graduation = self.get_all_graduation_config()
        return graduation.get("practical_skills", {})

    def get_graduation_settings(self) -> Dict:
        """Get global graduation settings."""
        config = self.get_practical_skills_config()
        return config.get("settings", {})

    def get_graduation_categories(self) -> Dict[str, Dict]:
        """
        Get all task categories for graduation tracking.

        Returns:
            Dict mapping category name to category config
        """
        config = self.get_practical_skills_config()
        return config.get("categories", {})

    def get_graduation_category(self, category_name: str) -> Optional[Dict]:
        """
        Get configuration for a specific task category.

        Args:
            category_name: e.g., 'email_drafting', 'code_help'

        Returns:
            Dict with threshold, prompts, skill_tips, celebration
        """
        categories = self.get_graduation_categories()
        return categories.get(category_name)

    def get_graduation_prompts(self, category_name: str) -> List[str]:
        """Get graduation prompts for a category."""
        category = self.get_graduation_category(category_name)
        if category:
            return category.get("graduation_prompts", [])
        return []

    def get_skill_tips(self, category_name: str) -> List[Dict]:
        """Get skill tips for a category."""
        category = self.get_graduation_category(category_name)
        if category:
            return category.get("skill_tips", [])
        return []

    def get_graduation_celebration(self, category_name: str) -> List[str]:
        """Get celebration messages for completing tasks independently."""
        category = self.get_graduation_category(category_name)
        if category:
            return category.get("celebration", [])
        return []

    def get_independence_config(self) -> Dict:
        """Get independence tracking configuration."""
        config = self.get_practical_skills_config()
        return config.get("independence", {})

    def get_independence_celebrations(self) -> List[str]:
        """Get general independence celebration messages."""
        independence = self.get_independence_config()
        return independence.get("celebration_messages", [])

    def get_independence_button_labels(self) -> List[str]:
        """Get button label options for 'I did it myself'."""
        independence = self.get_independence_config()
        return independence.get("button_labels", ["I did it myself!"])

    # ==================== HANDOFF ====================

    def get_all_handoff_config(self) -> Dict[str, Dict]:
        """Load all handoff configurations."""
        return self._load_directory("handoff")

    def get_contextual_templates_config(self) -> Dict:
        """Get contextual handoff templates configuration."""
        handoff = self.get_all_handoff_config()
        return handoff.get("contextual_templates", {})

    def get_handoff_settings(self) -> Dict:
        """Get handoff behavior settings."""
        config = self.get_contextual_templates_config()
        return config.get("settings", {})

    def get_handoff_context_rules(self) -> Dict[str, Dict]:
        """
        Get context detection rules for handoff templates.

        Returns:
            Dict mapping context name to rule config
        """
        config = self.get_contextual_templates_config()
        return config.get("context_rules", {})

    def get_handoff_templates(self) -> Dict[str, Dict]:
        """
        Get all handoff template categories.

        Returns:
            Dict mapping category name to template config
        """
        config = self.get_contextual_templates_config()
        return config.get("templates", {})

    def get_handoff_template_category(self, category: str) -> Optional[Dict]:
        """
        Get a specific handoff template category.

        Args:
            category: e.g., 'after_difficult_task', 'processing_decision'

        Returns:
            Dict with name, description, intro_prompts, messages
        """
        templates = self.get_handoff_templates()
        return templates.get(category)

    def get_handoff_intro_prompts(self, category: str) -> List[str]:
        """Get intro prompts for a handoff category."""
        template = self.get_handoff_template_category(category)
        if template:
            return template.get("intro_prompts", [])
        return []

    def get_handoff_messages(self, category: str, domain: str = None) -> List[str]:
        """
        Get handoff message templates for a category.

        Args:
            category: Template category (e.g., 'after_difficult_task')
            domain: Optional domain for domain-specific messages

        Returns:
            List of message templates
        """
        template = self.get_handoff_template_category(category)
        if not template:
            return []

        messages = template.get("messages", [])

        # Check for domain-specific messages first
        if domain and "by_domain" in template.get("messages", {}):
            by_domain = template["messages"].get("by_domain", {})
            domain_messages = by_domain.get(domain, by_domain.get("general", []))
            if domain_messages:
                return domain_messages

        # Return general messages
        result = []
        for msg_group in messages:
            if isinstance(msg_group, dict) and "templates" in msg_group:
                result.extend(msg_group.get("templates", []))
            elif isinstance(msg_group, str):
                result.append(msg_group)

        return result

    def get_handoff_follow_up_prompts(self, category: str) -> List[str]:
        """Get follow-up prompts for a handoff category."""
        template = self.get_handoff_template_category(category)
        if template:
            return template.get("follow_up_prompts", [])
        return []

    def get_handoff_follow_up_options(self) -> Dict:
        """Get self-report options for handoff follow-up."""
        config = self.get_contextual_templates_config()
        return config.get("follow_up_options", {})

    def get_handoff_celebrations(self, outcome: str = "reached_out") -> List[str]:
        """
        Get celebration messages for handoff outcomes.

        Args:
            outcome: 'reached_out', 'very_helpful', 'not_yet', etc.

        Returns:
            List of celebration messages
        """
        follow_up = self.get_handoff_follow_up_options()
        celebrations = follow_up.get("celebrations", {})
        return celebrations.get(outcome, [])

    def detect_handoff_context(
        self,
        emotional_weight: str = None,
        session_intent: str = None,
        domain: str = None,
        dependency_score: float = 0,
        is_late_night: bool = False,
        sessions_today: int = 0,
    ) -> str:
        """
        Detect the appropriate handoff context based on session state.

        Args:
            emotional_weight: 'high_weight', 'medium_weight', or 'low_weight'
            session_intent: 'practical', 'processing', 'emotional', 'connection'
            domain: Current conversation domain
            dependency_score: User's dependency score (0-10)
            is_late_night: Whether it's a late night session
            sessions_today: Number of sessions today

        Returns:
            Context category name (e.g., 'after_difficult_task')
        """
        rules = self.get_handoff_context_rules()

        # Check rules in priority order
        sorted_rules = sorted(rules.items(), key=lambda x: x[1].get("priority", 10))

        for context_name, rule in sorted_rules:
            triggers = rule.get("triggers", [])

            # Check if any triggers match
            for trigger in triggers:
                if trigger == "high_emotional_weight_task" and emotional_weight == "high_weight":
                    return context_name
                if trigger == "session_intent_processing" and session_intent == "processing":
                    return context_name
                if trigger.startswith("domain_") and domain == trigger.replace("domain_", ""):
                    return context_name
                if trigger == "high_dependency_score" and dependency_score >= 7:
                    return context_name
                if trigger == "late_night_session" and is_late_night:
                    return context_name
                if trigger == "multiple_sessions_today" and sessions_today >= 3:
                    return context_name

        return "general"

    # ==================== TRANSPARENCY ====================

    def get_all_transparency_config(self) -> Dict[str, Dict]:
        """Load all transparency configurations."""
        return self._load_directory("transparency")

    def get_explanations_config(self) -> Dict:
        """Get transparency explanations configuration."""
        transparency = self.get_all_transparency_config()
        return transparency.get("explanations", {})

    def get_transparency_settings(self) -> Dict:
        """Get transparency feature settings."""
        config = self.get_explanations_config()
        return config.get("settings", {})

    def get_domain_explanation(self, domain: str) -> Dict:
        """
        Get the explanation for a domain.

        Args:
            domain: e.g., 'logistics', 'relationships', 'health'

        Returns:
            Dict with name, icon, description, mode_note
        """
        config = self.get_explanations_config()
        explanations = config.get("domain_explanations", {})
        return explanations.get(
            domain, {"name": domain.title(), "description": f"Topic: {domain}", "mode_note": ""}
        )

    def get_mode_explanation(self, mode: str) -> Dict:
        """
        Get the explanation for a response mode.

        Args:
            mode: 'practical' or 'reflective'

        Returns:
            Dict with name, description, behaviors, no_behaviors
        """
        config = self.get_explanations_config()
        explanations = config.get("mode_explanations", {})
        return explanations.get(
            mode,
            {
                "name": mode.title(),
                "description": f"{mode.title()} mode",
                "behaviors": [],
                "no_behaviors": [],
            },
        )

    def get_emotional_weight_explanation(self, weight: str) -> Dict:
        """
        Get the explanation for an emotional weight level.

        Args:
            weight: 'high_weight', 'medium_weight', or 'low_weight'

        Returns:
            Dict with name, description, note
        """
        config = self.get_explanations_config()
        explanations = config.get("emotional_weight_explanations", {})
        return explanations.get(
            weight, {"name": weight.replace("_", " ").title(), "description": "", "note": ""}
        )

    def get_policy_explanation(self, policy_type: str) -> Dict:
        """
        Get the explanation for a policy action.

        Args:
            policy_type: e.g., 'crisis_stop', 'turn_limit_reached'

        Returns:
            Dict with name, description, reason, user_note
        """
        config = self.get_explanations_config()
        explanations = config.get("policy_explanations", {})
        return explanations.get(
            policy_type,
            {
                "name": policy_type.replace("_", " ").title(),
                "description": "A policy action was triggered.",
                "reason": "",
                "user_note": "",
            },
        )

    def get_risk_level_explanation(self, risk_weight: float) -> Dict:
        """
        Get the explanation for a risk level based on weight.

        Args:
            risk_weight: 0-10 risk score

        Returns:
            Dict with range, name, description
        """
        config = self.get_explanations_config()
        explanations = config.get("risk_level_explanations", {})

        if risk_weight >= 8:
            return explanations.get("high", {"name": "High Risk", "description": ""})
        elif risk_weight >= 6:
            return explanations.get("elevated", {"name": "Elevated Risk", "description": ""})
        elif risk_weight >= 3:
            return explanations.get("moderate", {"name": "Moderate Risk", "description": ""})
        else:
            return explanations.get("low", {"name": "Low Risk", "description": ""})

    def get_session_summary_config(self) -> Dict:
        """Get session summary configuration."""
        config = self.get_explanations_config()
        return config.get("session_summary", {})

    def get_session_summary_footer(self, session_type: str) -> List[str]:
        """
        Get footer messages for session summary.

        Args:
            session_type: 'all_practical', 'mixed', 'mostly_reflective',
                         'policy_fired', 'long_session'

        Returns:
            List of footer message strings
        """
        summary_config = self.get_session_summary_config()
        footers = summary_config.get("footer_messages", {})
        return footers.get(session_type, [])

    def get_transparency_ui_labels(self) -> Dict:
        """Get UI labels for transparency components."""
        config = self.get_explanations_config()
        return config.get("ui_labels", {})

    # ==================== WISDOM & IMMUNITY (PHASE 8) ====================

    def get_all_wisdom_config(self) -> Dict[str, Dict]:
        """Load all wisdom configurations."""
        return self._load_directory("wisdom")

    def get_wisdom_prompts_config(self) -> Dict:
        """Get wisdom prompts configuration."""
        wisdom = self.get_all_wisdom_config()
        return wisdom.get("prompts", {})

    def get_wisdom_settings(self) -> Dict:
        """Get wisdom feature settings."""
        config = self.get_wisdom_prompts_config()
        return config.get("settings", {})

    # --- Friend Mode ---

    def get_friend_mode_config(self) -> Dict:
        """Get 'What Would You Tell a Friend?' mode configuration."""
        config = self.get_wisdom_prompts_config()
        return config.get("friend_mode", {})

    def get_friend_mode_settings(self) -> Dict:
        """Get friend mode settings."""
        settings = self.get_wisdom_settings()
        return settings.get("friend_mode", {})

    def get_friend_mode_flip_prompt(self) -> str:
        """Get a random flip prompt for friend mode."""
        import random

        config = self.get_friend_mode_config()
        prompts = config.get("flip_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "If a friend came to you with this exact situation, what would you tell them?"

    def get_friend_mode_follow_up(self) -> str:
        """Get a random follow-up prompt for friend mode."""
        import random

        config = self.get_friend_mode_config()
        prompts = config.get("follow_up_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "Could that same wisdom apply to your situation?"

    def get_friend_mode_closing(self) -> str:
        """Get a random closing prompt for friend mode."""
        import random

        config = self.get_friend_mode_config()
        prompts = config.get("closing_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "You clearly know what you'd tell someone else. Trust that."

    def get_friend_mode_triggers(self) -> List[str]:
        """Get trigger phrases for friend mode."""
        config = self.get_friend_mode_config()
        return config.get("trigger_phrases", [])

    def should_trigger_friend_mode(
        self, user_input: str, intent: str = None, domain: str = None
    ) -> bool:
        """
        Check if friend mode should be triggered.

        Args:
            user_input: The user's message
            intent: Detected intent ('practical', 'processing', 'emotional', 'connection')
            domain: Current domain

        Returns:
            True if friend mode should trigger
        """
        settings = self.get_friend_mode_settings()
        if not settings.get("enabled", True):
            return False

        # Skip for practical intent
        if settings.get("skip_for_practical", True) and intent == "practical":
            return False

        # Check for processing intent trigger
        if settings.get("trigger_on_processing_intent", True) and intent == "processing":
            return True

        # Check for trigger domains
        trigger_domains = settings.get("trigger_domains", [])
        if domain and domain in trigger_domains:
            # Also check for "what should I do" type phrases
            triggers = self.get_friend_mode_triggers()
            text_lower = user_input.lower()
            if any(trigger in text_lower for trigger in triggers):
                return True

        # Check for "what should I do" phrases regardless of domain
        if settings.get("trigger_on_what_should_i_do", True):
            triggers = self.get_friend_mode_triggers()
            text_lower = user_input.lower()
            if any(trigger in text_lower for trigger in triggers):
                return True

        return False

    # --- Before You Send Pause ---

    def get_before_you_send_config(self) -> Dict:
        """Get 'Before You Send' pause configuration."""
        config = self.get_wisdom_prompts_config()
        return config.get("before_you_send", {})

    def get_before_you_send_settings(self) -> Dict:
        """Get before you send settings."""
        settings = self.get_wisdom_settings()
        return settings.get("before_you_send", {})

    def get_pause_prompt(self, category: str = "default") -> str:
        """
        Get a pause prompt for a specific task category.

        Args:
            category: Task category (resignation, difficult_conversation, etc.)

        Returns:
            Pause prompt string
        """
        import random

        config = self.get_before_you_send_config()
        prompts = config.get("pause_prompts", {})
        category_prompts = prompts.get(category, prompts.get("default", []))
        if category_prompts:
            return random.choice(category_prompts)
        return "Here's what you asked for. For important messages, consider waiting before sending."

    def should_suggest_pause(self, emotional_weight: str, task_category: str = None) -> bool:
        """
        Check if a pause should be suggested.

        Args:
            emotional_weight: 'high_weight', 'medium_weight', 'low_weight'
            task_category: Optional task category

        Returns:
            True if pause should be suggested
        """
        settings = self.get_before_you_send_settings()
        if not settings.get("enabled", True):
            return False

        # Check if weight is in trigger list
        trigger_weights = settings.get("trigger_weights", ["high_weight"])
        if emotional_weight not in trigger_weights:
            return False

        # Check skip weights
        skip_weights = settings.get("skip_weights", [])
        if emotional_weight in skip_weights:
            return False

        return True

    def detect_pause_category(self, user_input: str) -> str:
        """
        Detect the pause category for a message.

        Args:
            user_input: The user's original request

        Returns:
            Category name (resignation, difficult_conversation, etc.)
        """
        text_lower = user_input.lower()

        if any(w in text_lower for w in ["resign", "quit", "leaving", "two weeks"]):
            return "resignation"
        if any(w in text_lower for w in ["breakup", "break up", "dump", "ending it"]):
            return "relationship_endings"
        if any(w in text_lower for w in ["apology", "apologize", "sorry", "apolog"]):
            return "apologies"
        if any(w in text_lower for w in ["boundary", "boundaries", "limit", "saying no"]):
            return "boundary_setting"
        if any(w in text_lower for w in ["difficult", "hard conversation", "confront"]):
            return "difficult_conversation"

        return "default"

    # --- Reflection Journaling ---

    def get_journaling_config(self) -> Dict:
        """Get reflection journaling configuration."""
        config = self.get_wisdom_prompts_config()
        return config.get("journaling", {})

    def get_journaling_settings(self) -> Dict:
        """Get journaling settings."""
        settings = self.get_wisdom_settings()
        return settings.get("journaling", {})

    def get_journaling_intro(self) -> str:
        """Get a random journaling intro prompt."""
        import random

        config = self.get_journaling_config()
        prompts = config.get("intro_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "Would you like to write it out for yourself first? Sometimes putting thoughts on paper helps."

    def get_journaling_prompts(self, category: str = "general") -> List[str]:
        """
        Get journaling prompts for a category.

        Args:
            category: 'general', 'relationship', 'decision', 'apology'

        Returns:
            List of journaling prompts
        """
        config = self.get_journaling_config()
        prompts = config.get("prompts", {})
        return prompts.get(category, prompts.get("general", []))

    def get_journaling_closing(self) -> str:
        """Get a random journaling closing prompt."""
        import random

        config = self.get_journaling_config()
        prompts = config.get("closing_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "Keep what you wrote. The right words will come when you're ready."

    # --- Human Gate ---

    def get_human_gate_config(self) -> Dict:
        """Get 'Have You Talked to Someone?' gate configuration."""
        config = self.get_wisdom_prompts_config()
        return config.get("human_gate", {})

    def get_human_gate_settings(self) -> Dict:
        """Get human gate settings."""
        settings = self.get_wisdom_settings()
        return settings.get("human_gate", {})

    def get_human_gate_prompt(self) -> str:
        """Get a random gate prompt."""
        import random

        config = self.get_human_gate_config()
        prompts = config.get("gate_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "Have you talked to anyone you trust about this?"

    def get_human_gate_options(self) -> Dict:
        """Get the response options for human gate."""
        config = self.get_human_gate_config()
        return config.get("options", {})

    def get_human_gate_follow_up(self, response: str) -> str:
        """
        Get follow-up for a human gate response.

        Args:
            response: 'yes', 'not_yet', or 'no_one'

        Returns:
            Follow-up prompt string
        """
        import random

        options = self.get_human_gate_options()
        option = options.get(response, {})
        follow_ups = option.get("follow_up", [])
        if follow_ups:
            return random.choice(follow_ups)
        return ""

    def should_trigger_human_gate(
        self, domain: str = None, emotional_weight: str = None, gate_count: int = 0
    ) -> bool:
        """
        Check if human gate should be triggered.

        Args:
            domain: Current domain
            emotional_weight: Current emotional weight
            gate_count: Number of times gate has been shown this session

        Returns:
            True if gate should trigger
        """
        settings = self.get_human_gate_settings()
        if not settings.get("enabled", True):
            return False

        # Check max asks per session
        max_asks = settings.get("max_asks_per_session", 2)
        if gate_count >= max_asks:
            return False

        # Check trigger weights
        trigger_weights = settings.get("trigger_weights", [])
        if emotional_weight and emotional_weight in trigger_weights:
            return True

        # Check trigger domains
        trigger_domains = settings.get("trigger_domains", [])
        if domain and domain in trigger_domains:
            return True

        return False

    # --- AI Literacy ---

    def get_ai_literacy_config(self) -> Dict:
        """Get AI literacy moments configuration."""
        config = self.get_wisdom_prompts_config()
        return config.get("ai_literacy", {})

    def get_ai_literacy_settings(self) -> Dict:
        """Get AI literacy settings."""
        settings = self.get_wisdom_settings()
        return settings.get("ai_literacy", {})

    def get_ai_literacy_moment(self, trigger: str) -> Optional[str]:
        """
        Get an AI literacy moment for a trigger.

        Args:
            trigger: e.g., 'after_practical_task_no_engagement'

        Returns:
            Literacy message or None
        """
        config = self.get_ai_literacy_config()
        moments = config.get("moments", {})
        for moment_name, moment_config in moments.items():
            if moment_config.get("trigger") == trigger:
                return moment_config.get("message")
        return None

    def get_manipulation_patterns(self) -> Dict[str, Dict]:
        """Get manipulation patterns for 'Spot the Pattern' feature."""
        config = self.get_ai_literacy_config()
        return config.get("manipulation_patterns", {})

    # ==================== CONNECTION BUILDING (PHASE 12) ====================

    def get_all_connection_building(self) -> Dict[str, Dict]:
        """Load all connection building configurations."""
        return self._load_directory("connection_building")

    def get_signposts_config(self) -> Dict:
        """Get signposts configuration (types of places to find connection)."""
        connection = self.get_all_connection_building()
        return connection.get("signposts", {})

    def get_first_contact_config(self) -> Dict:
        """Get first contact templates configuration."""
        connection = self.get_all_connection_building()
        return connection.get("first_contact", {})

    def get_general_signposts(self) -> List[Dict]:
        """Get general signpost categories (not domain-specific)."""
        config = self.get_signposts_config()
        return config.get("general_signposts", [])

    def get_domain_signposts(self, domain: str) -> Dict:
        """
        Get signposts for a specific domain.

        Args:
            domain: e.g., 'relationships', 'money', 'health', 'spirituality'

        Returns:
            Dict with intro and categories, or empty dict
        """
        config = self.get_signposts_config()
        domain_signposts = config.get("domain_signposts", {})
        return domain_signposts.get(domain, {})

    def get_signpost_reflection_prompt(self) -> str:
        """Get a random reflection prompt for signposting."""
        import random

        config = self.get_signposts_config()
        prompts = config.get("reflection_prompts", [])
        if prompts:
            return random.choice(prompts)
        return "What kind of people do you feel most comfortable around?"

    def get_signpost_encouragement(self) -> str:
        """Get a random encouragement message for connection building."""
        import random

        config = self.get_signposts_config()
        messages = config.get("encouragement", [])
        if messages:
            return random.choice(messages)
        return "Building connection takes time. One small step is enough for today."

    def get_first_contact_situation(self, situation: str) -> Dict:
        """
        Get templates for a specific first-contact situation.

        Args:
            situation: e.g., 'at_a_group_or_meetup', 'turning_acquaintance_into_friend',
                      'reconnecting_with_someone_from_the_past', 'joining_a_new_community',
                      'asking_for_help_or_support'

        Returns:
            Dict with title, intro, tips, and templates
        """
        config = self.get_first_contact_config()
        situations = config.get("situations", {})
        return situations.get(situation, {})

    def get_all_first_contact_situations(self) -> Dict[str, Dict]:
        """Get all first-contact situation templates."""
        config = self.get_first_contact_config()
        return config.get("situations", {})

    def get_first_contact_principles(self) -> List[Dict]:
        """Get general principles for initiating connection."""
        config = self.get_first_contact_config()
        return config.get("general_principles", [])

    def get_first_contact_affirmation(self) -> str:
        """Get a random affirmation for people struggling with connection."""
        import random

        config = self.get_first_contact_config()
        affirmations = config.get("affirmations", [])
        if affirmations:
            return random.choice(affirmations)
        return "Finding connection as an adult is genuinely difficult. You're not broken for struggling with it."

    # ==================== CONNECTION STEERING ====================

    def get_connection_steering_config(self) -> Dict:
        """Get the full connection steering configuration."""
        connection = self.get_all_connection_building()
        return connection.get("steering_prompts", {})

    def get_isolation_signals(self) -> List[str]:
        """Get all isolation signal phrases (direct + passive) for keyword detection."""
        config = self.get_connection_steering_config()
        signals = config.get("isolation_signals", {})
        return signals.get("direct", []) + signals.get("passive", [])

    def get_steering_prompt_addition(self) -> str:
        """Get the background warmth modifier injected when steering is active."""
        config = self.get_connection_steering_config()
        return config.get("steering", {}).get("system_prompt_addition", "")

    # ==================== UTILITY METHODS ====================

    def clear_cache(self) -> None:
        """Clear the internal cache to force reload from files."""
        self._cache.clear()

    def reload(self) -> None:
        """Reload all scenarios from disk."""
        self.clear_cache()

    # ==================== PHASE 7: SUCCESS METRICS ====================

    def get_all_metrics_config(self) -> Dict:
        """Load all metrics configuration."""
        return self._load_directory("metrics")

    def get_success_metrics_config(self) -> Dict:
        """Get the success metrics configuration."""
        configs = self.get_all_metrics_config()
        return configs.get("success_metrics", {})

    def get_dashboard_config(self) -> Dict:
        """Get dashboard display configuration."""
        config = self.get_success_metrics_config()
        return config.get("dashboard", {})

    def get_anti_engagement_config(self) -> Dict:
        """Get anti-engagement scoring configuration."""
        config = self.get_success_metrics_config()
        return config.get("anti_engagement", {})

    def get_self_report_config(self) -> Dict:
        """Get self-report prompts configuration."""
        config = self.get_success_metrics_config()
        return config.get("self_reports", {})

    def get_metrics_thresholds(self) -> Dict:
        """Get time-based and usage thresholds."""
        config = self.get_success_metrics_config()
        return config.get("thresholds", {})

    def get_sensitive_categories(self) -> Dict:
        """Get what counts as 'sensitive' for metrics purposes."""
        config = self.get_success_metrics_config()
        return config.get("sensitive_categories", {})

    def get_dashboard_templates(self) -> Dict:
        """Get dashboard display message templates."""
        config = self.get_success_metrics_config()
        return config.get("dashboard_templates", {})

    def get_score_range_config(self, score: float) -> Dict:
        """
        Get the configuration for a given anti-engagement score.

        Args:
            score: The anti-engagement score (0-10)

        Returns:
            Dict with label, message, color for this score range
        """
        config = self.get_anti_engagement_config()
        ranges = config.get("score_ranges", {})

        for range_name in ["excellent", "good", "moderate", "concerning", "high"]:
            range_config = ranges.get(range_name, {})
            if score <= range_config.get("max", 10):
                return {
                    "level": range_name,
                    "label": range_config.get("label", "Unknown"),
                    "message": range_config.get("message", ""),
                    "color": range_config.get("color", "gray"),
                }

        return {"level": "high", "label": "Unknown", "message": "", "color": "gray"}

    def get_trend_message(self, metric: str, trend: str) -> str:
        """
        Get the appropriate message for a metric's trend.

        Args:
            metric: 'sensitive', 'connection', 'human_connections', etc.
            trend: 'down', 'up', 'stable'

        Returns:
            Human-readable trend message
        """
        config = self.get_dashboard_config()
        messages = config.get("trend_messages", {})

        key = f"{metric}_{trend}"
        return messages.get(key, "")

    def get_self_report_prompt(self, prompt_type: str) -> Dict:
        """
        Get a specific self-report prompt configuration.

        Args:
            prompt_type: 'handoff_followup', 'weekly_clarity', 'usage_reflection'

        Returns:
            Dict with question, options, celebration text
        """
        config = self.get_self_report_config()
        prompts = config.get("prompts", {})
        return prompts.get(prompt_type, {})

    def get_all_triggers_flat(self) -> Dict[str, str]:
        """
        Get a flat mapping of trigger word -> domain.
        Useful for quick lookups.

        IMPORTANT: Domains are processed in order of risk_weight (highest first).
        This ensures "friend is addicted" matches health (7.0) before relationships (5.0).
        """
        triggers = self.get_domain_triggers()
        weights = self.get_domain_weights()

        # Sort domains by risk_weight (highest first) so high-risk triggers take priority
        sorted_domains = sorted(triggers.keys(), key=lambda d: weights.get(d, 1.0), reverse=True)

        flat = {}
        for domain in sorted_domains:
            words = triggers.get(domain, [])
            for word in words:
                # Only add if not already present (higher-priority domain wins)
                word_lower = word.lower()
                if word_lower not in flat:
                    flat[word_lower] = domain
        return flat

    # ==================== SYSTEM DEFAULTS ====================

    def get_system_defaults(self) -> Dict:
        """Load system_defaults.yaml — the central tunables config.

        Returns the full dict from scenarios/config/system_defaults.yaml,
        or an empty dict if the file doesn't exist (all code falls back
        to hardcoded defaults).
        """
        cache_key = "system_defaults"
        if cache_key in self._cache:
            return self._cache[cache_key]

        config_file = self.scenarios_path / "config" / "system_defaults.yaml"
        if config_file.exists():
            result = self._load_yaml(config_file)
        else:
            result = {}

        self._cache[cache_key] = result
        return result

    def get_default(self, *keys, fallback=None):
        """Lookup a nested value from system_defaults.yaml.

        Usage:
            loader.get_default("session", "turn_limits", "logistics", fallback=30)
            loader.get_default("ollama", "max_input_length", fallback=5000)

        Returns fallback if any key in the chain is missing.
        """
        data = self.get_system_defaults()
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return fallback
            if data is None:
                return fallback
        return data


# Singleton instance for convenience
_loader_instance: Optional[ScenarioLoader] = None


def get_scenario_loader(scenarios_path: Optional[str] = None) -> ScenarioLoader:
    """
    Get the singleton ScenarioLoader instance.

    Args:
        scenarios_path: Optional path to scenarios directory.
                       Only used on first call.

    Returns:
        ScenarioLoader instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = ScenarioLoader(scenarios_path)
    return _loader_instance


def reset_scenario_loader() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _loader_instance
    _loader_instance = None
