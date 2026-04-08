"""
Typed data contracts for empathySync pipeline outputs.

These dataclasses define the shape of data flowing through the
classification and response pipeline. They replace fragile dicts
with typed, documented, IDE-friendly structures.

Backward compatibility:
    result["domain"]       # Works via __getitem__
    result.get("domain")   # Works via .get()
    result.domain          # The preferred new way

Migration strategy: Define contracts now, adopt gradually.
Methods that currently return dicts will switch to returning
these dataclasses once consumers are updated.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass
class RiskAssessment:
    """
    Output of RiskClassifier.classify().

    Represents a complete risk assessment for a user message,
    including domain detection, emotional analysis, and dependency scoring.
    """

    domain: str
    emotional_intensity: float
    emotional_weight: str
    emotional_weight_score: float
    dependency_risk: float
    risk_weight: float
    classification_method: str = "keyword"
    is_personal_distress: bool = False
    is_practical_technique: bool = False
    llm_confidence: float = 0.0
    intervention: Optional[Dict] = None

    def __post_init__(self):
        self.emotional_intensity = max(0.0, min(10.0, float(self.emotional_intensity)))
        self.dependency_risk = max(0.0, float(self.dependency_risk))
        self.risk_weight = max(0.0, float(self.risk_weight))
        self.llm_confidence = max(0.0, min(1.0, float(self.llm_confidence)))

    def __getitem__(self, key: str) -> Any:
        """Dict-style access for backward compatibility."""
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style .get() for backward compatibility."""
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskAssessment":
        """Create from a dict, ignoring unknown keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class LLMClassification:
    """
    Output of LLMClassifier.classify().

    Represents the LLM's understanding of a message before
    keyword-based enrichment by RiskClassifier.

    Phase 17.1 adds distress_level and distress_present for multi-signal routing.
    These allow the risk classifier to override the topic domain when the user
    is in genuine distress, even if the topic is otherwise practical.
    """

    domain: str
    emotional_intensity: float
    is_personal_distress: bool = False
    topic_summary: str = ""
    confidence: float = 0.0
    is_practical_technique: bool = False
    classification_method: str = "llm"
    distress_present: bool = False
    distress_level: str = "none"

    _VALID_DISTRESS_LEVELS = frozenset({"none", "low", "moderate", "high", "crisis"})

    def __post_init__(self):
        self.emotional_intensity = max(0.0, min(10.0, float(self.emotional_intensity)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.distress_level not in self._VALID_DISTRESS_LEVELS:
            self.distress_level = "none"
        if self.distress_level != "none":
            self.distress_present = True

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMClassification":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)
