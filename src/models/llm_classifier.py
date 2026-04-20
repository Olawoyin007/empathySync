"""
LLM-Based Intelligent Classifier

Uses the Ollama model to classify user messages with context awareness,
replacing brittle keyword matching for nuanced classification.

Part of Phase 9: LLM-Based Intelligent Classification
"""

import json
import re
import hashlib
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import OrderedDict

import logging
import yaml

# Pre-compiled regex patterns for JSON extraction from LLM responses.
# These run on every classification call — compiling once avoids repeated work.
_RE_JSON_STRICT = re.compile(r'\{[^{}]*"domain"[^{}]*\}', re.DOTALL)
_RE_JSON_PERMISSIVE = re.compile(r'\{.*?"domain".*?\}', re.DOTALL)

from models.enums import Domain

from config.settings import settings

logger = logging.getLogger(__name__)


class LRUCache:
    """Simple LRU cache for classification results"""

    def __init__(self, max_size: int = 100):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[Dict]:
        if key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # Remove oldest
                self.cache.popitem(last=False)
        self.cache[key] = value

    def clear(self):
        self.cache.clear()


class LLMClassifier:
    """
    Intelligent classifier using the Ollama LLM for context-aware classification.

    Features:
    - Context-aware: understands "breaking down" in political vs personal context
    - Fast-path: safety-critical keywords bypass LLM for immediate handling
    - Caching: avoids repeated calls for same/similar messages
    - Fallback: returns None if classification fails (caller uses keyword matching)
    """

    def __init__(self, config_path: Optional[str] = None, http_client: httpx.Client = None):
        """Initialize the LLM classifier with configuration.

        Args:
            config_path: Path to YAML config (default: scenarios/classification/llm_classifier.yaml)
            http_client: Injectable httpx.Client for testability and connection reuse.
                         If None, uses the shared module-level client.
        """
        self._http_client = http_client
        self.config_path = (
            config_path
            or Path(__file__).parent.parent.parent
            / "scenarios"
            / "classification"
            / "llm_classifier.yaml"
        )
        self.config = self._load_config()
        self.cache = LRUCache(max_size=self.config.get("cache", {}).get("max_entries", 100))
        self.ollama_url = f"{settings.OLLAMA_HOST}/api/generate"
        # Use dedicated classifier model if configured, otherwise fall back to main model
        self.model = settings.OLLAMA_CLASSIFIER_MODEL or settings.OLLAMA_MODEL

        # Pre-compile fast-path patterns for efficiency
        self._fast_path_crisis = [p.lower() for p in self.config.get("fast_path_crisis", [])]
        self._fast_path_harmful = [p.lower() for p in self.config.get("fast_path_harmful", [])]

        model_note = ""
        if settings.OLLAMA_CLASSIFIER_MODEL:
            model_note = f" (dedicated: {self.model})"
        else:
            model_note = f" (shared: {self.model})"
        logger.info(f"LLMClassifier initialized. Enabled: {self.is_enabled()}{model_note}")

    @property
    def http_client(self) -> httpx.Client:
        """Lazy-resolved HTTP client — injected or shared singleton."""
        if self._http_client is not None:
            return self._http_client
        from utils.http_client import get_http_client

        return get_http_client()

    def _load_config(self) -> Dict:
        """Load classification configuration from YAML"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, "r") as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning(f"LLM classifier config not found at {self.config_path}")
                return {"enabled": False}
        except Exception as e:
            logger.error(f"Error loading LLM classifier config: {e}")
            return {"enabled": False}

    def reload_config(self):
        """Reload configuration from disk"""
        self.config = self._load_config()
        self._fast_path_crisis = [p.lower() for p in self.config.get("fast_path_crisis", [])]
        self._fast_path_harmful = [p.lower() for p in self.config.get("fast_path_harmful", [])]
        self.cache.clear()
        logger.info("LLM classifier config reloaded")

    def is_enabled(self) -> bool:
        """Check if LLM classification is enabled"""
        return self.config.get("enabled", False)

    def _check_fast_path(self, message: str) -> Optional[Dict]:
        """
        Check if message matches safety-critical patterns.
        These bypass LLM classification entirely for safety.

        Returns classification dict if fast-path triggered, None otherwise.
        """
        message_lower = message.lower()

        # Check crisis patterns
        for pattern in self._fast_path_crisis:
            if pattern in message_lower:
                logger.info(f"Fast-path triggered: crisis pattern '{pattern}'")
                return {
                    "domain": "crisis",
                    "emotional_intensity": 10.0,
                    "is_personal_distress": True,
                    "is_practical_technique": False,
                    "confidence": 1.0,
                    "classification_method": "fast_path_crisis",
                    "distress_level": "crisis",
                    "distress_present": True,
                }

        # Check harmful patterns
        for pattern in self._fast_path_harmful:
            if pattern in message_lower:
                logger.info(f"Fast-path triggered: harmful pattern '{pattern}'")
                return {
                    "domain": "harmful",
                    "emotional_intensity": 0.0,
                    "is_personal_distress": False,
                    "is_practical_technique": False,
                    "confidence": 1.0,
                    "classification_method": "fast_path_harmful",
                    "distress_level": "none",
                    "distress_present": False,
                }

        return None

    def _get_cache_key(self, message: str, recent_context: str = "") -> str:
        """Generate cache key from message and context"""
        content = f"{message}|{recent_context[:200]}"  # Limit context for key
        return hashlib.md5(content.encode()).hexdigest()

    def _build_prompt(self, message: str, recent_context: str = "") -> str:
        """Build the classification prompt"""
        template = self.config.get("prompt_template", "")

        # Build few-shot examples
        examples = self.config.get("examples", [])
        example_text = ""
        if examples:
            example_text = "\nExamples:\n"
            for ex in examples[:3]:  # Limit to 3 examples to save tokens
                example_text += f'- "{ex["message"]}" → {json.dumps(ex["classification"])}\n'

        prompt = template.format(
            message=message,
            recent_context=recent_context[:500] if recent_context else "No prior context",
        )

        # Add examples after the template
        if example_text and "{examples}" not in prompt:
            prompt = prompt.replace("Return JSON:", f"{example_text}\nReturn JSON:")

        return prompt

    def _parse_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response with error handling"""
        try:
            # Try to find JSON in the response
            # LLMs sometimes add extra text around the JSON

            # First, try direct parse
            try:
                return json.loads(response.strip())
            except json.JSONDecodeError:
                pass

            # Try to extract JSON from response using pre-compiled patterns
            for pattern in (_RE_JSON_STRICT, _RE_JSON_PERMISSIVE):
                match = pattern.search(response)
                if match:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        continue

            logger.warning(f"Could not parse JSON from LLM response: {response[:200]}")
            return None

        except Exception as e:
            logger.error(f"Error parsing LLM classification response: {e}")
            return None

    def _validate_classification(self, result: Dict) -> Optional[Dict]:
        """Validate and normalize classification result"""
        if not isinstance(result, dict):
            return None

        # Check required fields
        if "domain" not in result:
            return None

        # Normalize domain
        valid_domains = {d.value for d in Domain}
        domain = result.get("domain", "").lower()
        if domain not in valid_domains:
            # Try to map close matches
            domain_map = {
                "practical": "logistics",
                "task": "logistics",
                "finance": "money",
                "financial": "money",
                "medical": "health",
                "mental": "health",
                "religion": "spirituality",
                "existential": "spirituality",
                "emotion": "emotional",
                "feelings": "emotional",
                "relationship": "relationships",
                "family": "relationships",
                "danger": "crisis",
                "emergency": "crisis",
                "illegal": "harmful",
                "violence": "harmful",
            }
            domain = domain_map.get(domain, "logistics")  # Default to logistics

        # Normalize emotional_intensity
        intensity = result.get("emotional_intensity", 0)
        try:
            intensity = float(intensity)
            intensity = max(0, min(10, intensity))  # Clamp to 0-10
        except (TypeError, ValueError):
            intensity = 5.0  # Default to middle

        # Normalize is_personal_distress
        is_distress = result.get("is_personal_distress", False)
        if isinstance(is_distress, str):
            is_distress = is_distress.lower() in ("true", "yes", "1")

        # Normalize is_practical_technique (Phase 9.1)
        # This distinguishes "how do I do X?" from "should I do X?"
        is_technique = result.get("is_practical_technique", False)
        if isinstance(is_technique, str):
            is_technique = is_technique.lower() in ("true", "yes", "1")

        # Normalize confidence
        confidence = result.get("confidence", 0.7)
        try:
            confidence = float(confidence)
            confidence = max(0, min(1, confidence))
        except (TypeError, ValueError):
            confidence = 0.7

        # Phase 17.1: Normalize distress_level and distress_present
        valid_distress_levels = {"none", "low", "moderate", "high", "crisis"}
        distress_level = result.get("distress_level", "none")
        if isinstance(distress_level, str):
            distress_level = distress_level.lower()
        if distress_level not in valid_distress_levels:
            distress_level = "none"
        distress_present = distress_level != "none"

        return {
            "domain": domain,
            "emotional_intensity": intensity,
            "is_personal_distress": bool(is_distress),
            "is_practical_technique": bool(is_technique),
            "confidence": confidence,
            "classification_method": "llm",
            "distress_level": distress_level,
            "distress_present": distress_present,
        }

    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama API for classification"""
        timeout_ms = self.config.get("timeout_ms", 10000)
        temperature = self.config.get("temperature", 0.1)
        max_tokens = self.config.get("max_tokens", 200)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "top_p": 0.9, "num_predict": max_tokens},
        }

        try:
            timeout_secs = timeout_ms / 1000
            response = self.http_client.post(self.ollama_url, json=payload, timeout=timeout_secs)
            response.raise_for_status()

            result = response.json()
            return result.get("response", "").strip()

        except httpx.TimeoutException:
            logger.warning("LLM classification timed out")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM classification HTTP error: {e.response.status_code}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"LLM classification API error: {e}")
            return None

    def classify(
        self, message: str, conversation_history: List[Dict] = None, use_cache: bool = True
    ) -> Optional[Dict]:
        """
        Classify a user message using the LLM.

        Args:
            message: The user's message to classify
            conversation_history: Recent conversation for context
            use_cache: Whether to use cached results

        Returns:
            Classification dict with domain, emotional_intensity, etc.
            Returns None if classification fails (caller should use keyword fallback)
        """
        if not message or not message.strip():
            return None

        # Truncate oversized input before classification
        MAX_CLASSIFY_LENGTH = 5000
        if len(message) > MAX_CLASSIFY_LENGTH:
            logger.warning(
                f"Truncating message from {len(message)} to {MAX_CLASSIFY_LENGTH} chars for classification"
            )
            message = message[:MAX_CLASSIFY_LENGTH]

        # Fast-path runs BEFORE is_enabled() check — safety-critical patterns
        # must be caught even when LLM_CLASSIFICATION_ENABLED=false.
        fast_path_result = self._check_fast_path(message)
        if fast_path_result:
            return fast_path_result

        if not self.is_enabled():
            logger.debug("LLM classification disabled")
            return None

        # Build context from conversation history
        recent_context = ""
        if conversation_history:
            recent_msgs = conversation_history[-10:]  # Last 5 exchanges
            recent_context = "\n".join(
                [
                    f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}"
                    for msg in recent_msgs
                ]
            )

        # Check cache
        if use_cache and self.config.get("cache", {}).get("enabled", True):
            cache_key = self._get_cache_key(message, recent_context)
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for classification")
                cached["classification_method"] = "llm_cached"
                return cached

        # Build and send prompt
        prompt = self._build_prompt(message, recent_context)

        logger.debug(f"Calling LLM for classification: {message[:50]}...")
        response = self._call_ollama(prompt)

        if not response:
            return None

        # Parse and validate response
        parsed = self._parse_response(response)
        if not parsed:
            return None

        validated = self._validate_classification(parsed)
        if not validated:
            return None

        # Check confidence threshold
        confidence_threshold = self.config.get("confidence_threshold", 0.6)
        if validated["confidence"] < confidence_threshold:
            logger.info(
                f"LLM confidence {validated['confidence']} below threshold {confidence_threshold}"
            )
            return None  # Fall back to keyword matching

        # Cache result
        if use_cache and self.config.get("cache", {}).get("enabled", True):
            cache_key = self._get_cache_key(message, recent_context)
            self.cache.set(cache_key, validated)

        logger.info(
            f"LLM classification: domain={validated['domain']}, "
            f"intensity={validated['emotional_intensity']}, "
            f"confidence={validated['confidence']}"
        )

        return validated

    def clear_cache(self):
        """Clear the classification cache"""
        self.cache.clear()
        logger.info("LLM classification cache cleared")


# Singleton instance
_llm_classifier_instance: Optional[LLMClassifier] = None


def get_llm_classifier() -> LLMClassifier:
    """Get or create the singleton LLMClassifier instance"""
    global _llm_classifier_instance
    if _llm_classifier_instance is None:
        _llm_classifier_instance = LLMClassifier()
    return _llm_classifier_instance
