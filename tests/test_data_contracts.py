"""
Tests for src/models/data_contracts.py

Covers:
- RiskAssessment creation with valid and invalid data
- LLMClassification creation with valid and invalid data
- Dict-compatible access (__getitem__, .get())
- to_dict() conversion
- from_dict() factory method
- __post_init__ validation (clamping, type coercion, boundary values)
- Default values
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from models.data_contracts import RiskAssessment, LLMClassification


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------


class TestRiskAssessmentCreation:
    """Test RiskAssessment instantiation with various inputs."""

    def test_create_with_required_fields(self):
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=3.0,
            risk_weight=7.0,
        )
        assert ra.domain == "health"
        assert ra.emotional_intensity == 5.0
        assert ra.emotional_weight == "medium_weight"
        assert ra.emotional_weight_score == 5.0
        assert ra.dependency_risk == 3.0
        assert ra.risk_weight == 7.0

    def test_default_values(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=1.0,
        )
        assert ra.classification_method == "keyword"
        assert ra.is_personal_distress is False
        assert ra.is_practical_technique is False
        assert ra.llm_confidence == 0.0
        assert ra.intervention is None

    def test_create_with_all_fields(self):
        intervention = {"level": "mild", "message": "Consider a break"}
        ra = RiskAssessment(
            domain="emotional",
            emotional_intensity=8.0,
            emotional_weight="high_weight",
            emotional_weight_score=8.0,
            dependency_risk=6.0,
            risk_weight=9.0,
            classification_method="llm",
            is_personal_distress=True,
            is_practical_technique=False,
            llm_confidence=0.85,
            intervention=intervention,
        )
        assert ra.classification_method == "llm"
        assert ra.is_personal_distress is True
        assert ra.is_practical_technique is False
        assert ra.llm_confidence == 0.85
        assert ra.intervention == intervention

    def test_missing_required_field_raises(self):
        with pytest.raises(TypeError):
            RiskAssessment(
                domain="health",
                emotional_intensity=5.0,
                # missing emotional_weight, emotional_weight_score, dependency_risk, risk_weight
            )


class TestRiskAssessmentPostInit:
    """Test __post_init__ clamping and type coercion."""

    def test_emotional_intensity_clamped_high(self):
        ra = RiskAssessment(
            domain="crisis",
            emotional_intensity=15.0,
            emotional_weight="high_weight",
            emotional_weight_score=10.0,
            dependency_risk=0.0,
            risk_weight=10.0,
        )
        assert ra.emotional_intensity == 10.0

    def test_emotional_intensity_clamped_low(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=-5.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=1.0,
        )
        assert ra.emotional_intensity == 0.0

    def test_emotional_intensity_boundary_zero(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=1.0,
        )
        assert ra.emotional_intensity == 0.0

    def test_emotional_intensity_boundary_ten(self):
        ra = RiskAssessment(
            domain="crisis",
            emotional_intensity=10.0,
            emotional_weight="high_weight",
            emotional_weight_score=10.0,
            dependency_risk=0.0,
            risk_weight=10.0,
        )
        assert ra.emotional_intensity == 10.0

    def test_dependency_risk_clamped_low(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=-3.0,
            risk_weight=1.0,
        )
        assert ra.dependency_risk == 0.0

    def test_dependency_risk_no_upper_clamp(self):
        """dependency_risk uses max(0.0, ...) only - no upper clamp."""
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=99.0,
            risk_weight=1.0,
        )
        assert ra.dependency_risk == 99.0

    def test_risk_weight_clamped_low(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=-1.0,
        )
        assert ra.risk_weight == 0.0

    def test_risk_weight_no_upper_clamp(self):
        """risk_weight uses max(0.0, ...) only - no upper clamp."""
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=100.0,
        )
        assert ra.risk_weight == 100.0

    def test_llm_confidence_clamped_high(self):
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=0.0,
            risk_weight=7.0,
            llm_confidence=1.5,
        )
        assert ra.llm_confidence == 1.0

    def test_llm_confidence_clamped_low(self):
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=0.0,
            risk_weight=7.0,
            llm_confidence=-0.5,
        )
        assert ra.llm_confidence == 0.0

    def test_llm_confidence_boundary_zero(self):
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=0.0,
            risk_weight=7.0,
            llm_confidence=0.0,
        )
        assert ra.llm_confidence == 0.0

    def test_llm_confidence_boundary_one(self):
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=0.0,
            risk_weight=7.0,
            llm_confidence=1.0,
        )
        assert ra.llm_confidence == 1.0

    def test_int_coerced_to_float(self):
        """Integer values should be coerced to float by __post_init__."""
        ra = RiskAssessment(
            domain="health",
            emotional_intensity=5,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=3,
            risk_weight=7,
            llm_confidence=1,
        )
        assert isinstance(ra.emotional_intensity, float)
        assert isinstance(ra.dependency_risk, float)
        assert isinstance(ra.risk_weight, float)
        assert isinstance(ra.llm_confidence, float)

    def test_string_numeric_coerced_to_float(self):
        """String numeric values should be coerced to float by float() call."""
        ra = RiskAssessment(
            domain="health",
            emotional_intensity="5",
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk="3",
            risk_weight="7",
            llm_confidence="0.5",
        )
        assert ra.emotional_intensity == 5.0
        assert ra.dependency_risk == 3.0
        assert ra.risk_weight == 7.0
        assert ra.llm_confidence == 0.5

    def test_non_numeric_string_raises(self):
        with pytest.raises(ValueError):
            RiskAssessment(
                domain="health",
                emotional_intensity="not_a_number",
                emotional_weight="medium_weight",
                emotional_weight_score=5.0,
                dependency_risk=0.0,
                risk_weight=7.0,
            )


class TestRiskAssessmentDictAccess:
    """Test __getitem__ and .get() for backward compatibility."""

    @pytest.fixture
    def risk_assessment(self):
        return RiskAssessment(
            domain="money",
            emotional_intensity=4.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=2.0,
            risk_weight=6.0,
            classification_method="llm",
            llm_confidence=0.9,
        )

    def test_getitem_existing_field(self, risk_assessment):
        assert risk_assessment["domain"] == "money"
        assert risk_assessment["emotional_intensity"] == 4.0
        assert risk_assessment["classification_method"] == "llm"

    def test_getitem_missing_field_raises(self, risk_assessment):
        with pytest.raises(AttributeError):
            _ = risk_assessment["nonexistent_field"]

    def test_get_existing_field(self, risk_assessment):
        assert risk_assessment.get("domain") == "money"
        assert risk_assessment.get("llm_confidence") == 0.9

    def test_get_missing_field_returns_default(self, risk_assessment):
        assert risk_assessment.get("nonexistent_field") is None
        assert risk_assessment.get("nonexistent_field", "fallback") == "fallback"

    def test_get_none_field(self, risk_assessment):
        assert risk_assessment.get("intervention") is None

    def test_get_false_field_not_confused_with_missing(self, risk_assessment):
        """Ensure .get() returns False (not default) for fields that are False."""
        assert risk_assessment.get("is_personal_distress", "WRONG") is False


class TestRiskAssessmentToDict:
    """Test to_dict() conversion."""

    def test_to_dict_returns_plain_dict(self):
        ra = RiskAssessment(
            domain="relationships",
            emotional_intensity=6.0,
            emotional_weight="high_weight",
            emotional_weight_score=8.0,
            dependency_risk=1.0,
            risk_weight=5.0,
        )
        d = ra.to_dict()
        assert isinstance(d, dict)
        assert d["domain"] == "relationships"
        assert d["emotional_intensity"] == 6.0
        assert d["emotional_weight"] == "high_weight"
        assert d["emotional_weight_score"] == 8.0
        assert d["dependency_risk"] == 1.0
        assert d["risk_weight"] == 5.0
        assert d["classification_method"] == "keyword"
        assert d["is_personal_distress"] is False
        assert d["is_practical_technique"] is False
        assert d["llm_confidence"] == 0.0
        assert d["intervention"] is None

    def test_to_dict_includes_intervention(self):
        intervention = {"level": "high", "message": "Please take a break"}
        ra = RiskAssessment(
            domain="emotional",
            emotional_intensity=9.0,
            emotional_weight="high_weight",
            emotional_weight_score=9.0,
            dependency_risk=8.0,
            risk_weight=9.0,
            intervention=intervention,
        )
        d = ra.to_dict()
        assert d["intervention"] == intervention

    def test_to_dict_is_independent_copy(self):
        """Modifying the dict should not affect the dataclass."""
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=1.0,
        )
        d = ra.to_dict()
        d["domain"] = "crisis"
        assert ra.domain == "logistics"


class TestRiskAssessmentFromDict:
    """Test from_dict() class method."""

    def test_from_dict_with_all_fields(self):
        data = {
            "domain": "health",
            "emotional_intensity": 7.0,
            "emotional_weight": "high_weight",
            "emotional_weight_score": 8.0,
            "dependency_risk": 2.0,
            "risk_weight": 7.0,
            "classification_method": "llm",
            "is_personal_distress": True,
            "is_practical_technique": False,
            "llm_confidence": 0.95,
            "intervention": None,
        }
        ra = RiskAssessment.from_dict(data)
        assert ra.domain == "health"
        assert ra.emotional_intensity == 7.0
        assert ra.classification_method == "llm"
        assert ra.llm_confidence == 0.95

    def test_from_dict_ignores_unknown_keys(self):
        data = {
            "domain": "logistics",
            "emotional_intensity": 0.0,
            "emotional_weight": "low_weight",
            "emotional_weight_score": 2.0,
            "dependency_risk": 0.0,
            "risk_weight": 1.0,
            "unknown_field": "should be ignored",
            "another_unknown": 42,
        }
        ra = RiskAssessment.from_dict(data)
        assert ra.domain == "logistics"
        assert not hasattr(ra, "unknown_field")

    def test_from_dict_missing_required_raises(self):
        data = {"domain": "health"}
        with pytest.raises(TypeError):
            RiskAssessment.from_dict(data)

    def test_from_dict_roundtrip(self):
        original = RiskAssessment(
            domain="spirituality",
            emotional_intensity=3.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=1.0,
            risk_weight=4.0,
            classification_method="llm",
            llm_confidence=0.7,
        )
        rebuilt = RiskAssessment.from_dict(original.to_dict())
        assert rebuilt.to_dict() == original.to_dict()


# ---------------------------------------------------------------------------
# LLMClassification
# ---------------------------------------------------------------------------


class TestLLMClassificationCreation:
    """Test LLMClassification instantiation."""

    def test_create_with_required_fields(self):
        lc = LLMClassification(
            domain="health",
            emotional_intensity=6.0,
        )
        assert lc.domain == "health"
        assert lc.emotional_intensity == 6.0

    def test_default_values(self):
        lc = LLMClassification(
            domain="logistics",
            emotional_intensity=0.0,
        )
        assert lc.is_personal_distress is False
        assert lc.topic_summary == ""
        assert lc.confidence == 0.0
        assert lc.is_practical_technique is False
        assert lc.classification_method == "llm"

    def test_create_with_all_fields(self):
        lc = LLMClassification(
            domain="money",
            emotional_intensity=4.0,
            is_personal_distress=True,
            topic_summary="User asking about debt",
            confidence=0.92,
            is_practical_technique=True,
            classification_method="llm",
        )
        assert lc.is_personal_distress is True
        assert lc.topic_summary == "User asking about debt"
        assert lc.confidence == 0.92
        assert lc.is_practical_technique is True

    def test_missing_required_field_raises(self):
        with pytest.raises(TypeError):
            LLMClassification(domain="health")  # missing emotional_intensity

        with pytest.raises(TypeError):
            LLMClassification(emotional_intensity=5.0)  # missing domain


class TestLLMClassificationPostInit:
    """Test __post_init__ clamping and coercion."""

    def test_emotional_intensity_clamped_high(self):
        lc = LLMClassification(domain="crisis", emotional_intensity=20.0)
        assert lc.emotional_intensity == 10.0

    def test_emotional_intensity_clamped_low(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=-3.0)
        assert lc.emotional_intensity == 0.0

    def test_emotional_intensity_boundary_zero(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0)
        assert lc.emotional_intensity == 0.0

    def test_emotional_intensity_boundary_ten(self):
        lc = LLMClassification(domain="crisis", emotional_intensity=10.0)
        assert lc.emotional_intensity == 10.0

    def test_confidence_clamped_high(self):
        lc = LLMClassification(domain="health", emotional_intensity=5.0, confidence=2.0)
        assert lc.confidence == 1.0

    def test_confidence_clamped_low(self):
        lc = LLMClassification(domain="health", emotional_intensity=5.0, confidence=-0.5)
        assert lc.confidence == 0.0

    def test_confidence_boundary_zero(self):
        lc = LLMClassification(domain="health", emotional_intensity=5.0, confidence=0.0)
        assert lc.confidence == 0.0

    def test_confidence_boundary_one(self):
        lc = LLMClassification(domain="health", emotional_intensity=5.0, confidence=1.0)
        assert lc.confidence == 1.0

    def test_int_coerced_to_float(self):
        lc = LLMClassification(domain="health", emotional_intensity=7, confidence=1)
        assert isinstance(lc.emotional_intensity, float)
        assert isinstance(lc.confidence, float)

    def test_string_numeric_coerced_to_float(self):
        lc = LLMClassification(domain="health", emotional_intensity="8", confidence="0.5")
        assert lc.emotional_intensity == 8.0
        assert lc.confidence == 0.5

    def test_non_numeric_string_raises(self):
        with pytest.raises(ValueError):
            LLMClassification(domain="health", emotional_intensity="bad")


class TestLLMClassificationDictAccess:
    """Test __getitem__ and .get() for backward compatibility."""

    @pytest.fixture
    def llm_classification(self):
        return LLMClassification(
            domain="relationships",
            emotional_intensity=5.0,
            is_personal_distress=True,
            topic_summary="relationship advice",
            confidence=0.88,
            is_practical_technique=False,
        )

    def test_getitem_existing_field(self, llm_classification):
        assert llm_classification["domain"] == "relationships"
        assert llm_classification["emotional_intensity"] == 5.0
        assert llm_classification["topic_summary"] == "relationship advice"

    def test_getitem_missing_field_raises(self, llm_classification):
        with pytest.raises(AttributeError):
            _ = llm_classification["nonexistent"]

    def test_get_existing_field(self, llm_classification):
        assert llm_classification.get("domain") == "relationships"
        assert llm_classification.get("confidence") == 0.88

    def test_get_missing_field_returns_default(self, llm_classification):
        assert llm_classification.get("missing") is None
        assert llm_classification.get("missing", 42) == 42

    def test_get_empty_string_field_not_confused_with_missing(self):
        """Ensure .get() returns '' (not default) for empty string fields."""
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0)
        assert lc.get("topic_summary", "WRONG") == ""

    def test_get_false_field_not_confused_with_missing(self, llm_classification):
        assert llm_classification.get("is_practical_technique", "WRONG") is False


class TestLLMClassificationToDict:
    """Test to_dict() conversion."""

    def test_to_dict_returns_plain_dict(self):
        lc = LLMClassification(
            domain="spirituality",
            emotional_intensity=3.0,
            topic_summary="meditation question",
            confidence=0.75,
            is_practical_technique=True,
        )
        d = lc.to_dict()
        assert isinstance(d, dict)
        assert d["domain"] == "spirituality"
        assert d["emotional_intensity"] == 3.0
        assert d["is_personal_distress"] is False
        assert d["topic_summary"] == "meditation question"
        assert d["confidence"] == 0.75
        assert d["is_practical_technique"] is True
        assert d["classification_method"] == "llm"

    def test_to_dict_has_all_fields(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0)
        d = lc.to_dict()
        expected_keys = {
            "domain",
            "emotional_intensity",
            "is_personal_distress",
            "topic_summary",
            "confidence",
            "is_practical_technique",
            "classification_method",
            "distress_level",
            "distress_present",
            "isolation_level",
            "isolation_detected",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_is_independent_copy(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0)
        d = lc.to_dict()
        d["domain"] = "crisis"
        assert lc.domain == "logistics"


class TestLLMClassificationFromDict:
    """Test from_dict() class method."""

    def test_from_dict_with_all_fields(self):
        data = {
            "domain": "money",
            "emotional_intensity": 4.0,
            "is_personal_distress": False,
            "topic_summary": "budgeting",
            "confidence": 0.8,
            "is_practical_technique": True,
            "classification_method": "llm",
        }
        lc = LLMClassification.from_dict(data)
        assert lc.domain == "money"
        assert lc.confidence == 0.8
        assert lc.is_practical_technique is True

    def test_from_dict_ignores_unknown_keys(self):
        data = {
            "domain": "logistics",
            "emotional_intensity": 0.0,
            "extra_key": "ignored",
        }
        lc = LLMClassification.from_dict(data)
        assert lc.domain == "logistics"
        assert not hasattr(lc, "extra_key")

    def test_from_dict_missing_required_raises(self):
        with pytest.raises(TypeError):
            LLMClassification.from_dict({"domain": "health"})

    def test_from_dict_roundtrip(self):
        original = LLMClassification(
            domain="emotional",
            emotional_intensity=7.5,
            is_personal_distress=True,
            topic_summary="feeling overwhelmed",
            confidence=0.91,
        )
        rebuilt = LLMClassification.from_dict(original.to_dict())
        assert rebuilt.to_dict() == original.to_dict()


# ---------------------------------------------------------------------------
# Cross-cutting edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases that apply to both dataclasses."""

    def test_risk_assessment_with_zero_values(self):
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=0.0,
            dependency_risk=0.0,
            risk_weight=0.0,
        )
        assert ra.emotional_intensity == 0.0
        assert ra.dependency_risk == 0.0
        assert ra.risk_weight == 0.0

    def test_llm_classification_with_zero_values(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0, confidence=0.0)
        assert lc.emotional_intensity == 0.0
        assert lc.confidence == 0.0

    def test_risk_assessment_intervention_mutable(self):
        """Intervention dict should be the actual object, not a copy."""
        intervention = {"level": "mild", "message": "test"}
        ra = RiskAssessment(
            domain="emotional",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=5.0,
            risk_weight=5.0,
            intervention=intervention,
        )
        assert ra.intervention is intervention

    def test_risk_assessment_empty_intervention_dict(self):
        ra = RiskAssessment(
            domain="emotional",
            emotional_intensity=5.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=5.0,
            risk_weight=5.0,
            intervention={},
        )
        assert ra.intervention == {}

    def test_domain_accepts_enum_values(self):
        """Domain field should accept string enum values transparently."""
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=0.0,
            emotional_weight="low_weight",
            emotional_weight_score=2.0,
            dependency_risk=0.0,
            risk_weight=1.0,
        )
        assert ra.domain == "logistics"

        lc = LLMClassification(domain="crisis", emotional_intensity=10.0)
        assert lc.domain == "crisis"

    def test_large_float_values(self):
        """Very large floats should not cause errors; only clamped fields are bounded."""
        ra = RiskAssessment(
            domain="logistics",
            emotional_intensity=999.0,  # clamped to 10
            emotional_weight="low_weight",
            emotional_weight_score=999.0,  # not clamped by post_init
            dependency_risk=999.0,  # not upper-clamped
            risk_weight=999.0,  # not upper-clamped
            llm_confidence=999.0,  # clamped to 1.0
        )
        assert ra.emotional_intensity == 10.0
        assert ra.emotional_weight_score == 999.0
        assert ra.dependency_risk == 999.0
        assert ra.risk_weight == 999.0
        assert ra.llm_confidence == 1.0

    def test_risk_assessment_attribute_access_and_dict_access_match(self):
        ra = RiskAssessment(
            domain="money",
            emotional_intensity=4.0,
            emotional_weight="medium_weight",
            emotional_weight_score=5.0,
            dependency_risk=2.0,
            risk_weight=6.0,
        )
        assert ra.domain == ra["domain"]
        assert ra.emotional_intensity == ra["emotional_intensity"]
        assert ra.domain == ra.get("domain")

    def test_llm_classification_attribute_access_and_dict_access_match(self):
        lc = LLMClassification(domain="health", emotional_intensity=5.0, confidence=0.8)
        assert lc.domain == lc["domain"]
        assert lc.confidence == lc["confidence"]
        assert lc.domain == lc.get("domain")


# ---------------------------------------------------------------------------
# LLMClassification isolation fields (connection steering)
# ---------------------------------------------------------------------------


class TestLLMClassificationIsolationFields:
    """Tests for isolation_detected and isolation_level fields added for connection steering."""

    def test_defaults_to_no_isolation(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0)
        assert lc.isolation_level == "none"
        assert lc.isolation_detected is False

    def test_active_isolation_sets_detected(self):
        lc = LLMClassification(
            domain="emotional", emotional_intensity=7.0, isolation_level="active"
        )
        assert lc.isolation_detected is True
        assert lc.isolation_level == "active"

    def test_passive_isolation_sets_detected(self):
        lc = LLMClassification(
            domain="emotional", emotional_intensity=4.0, isolation_level="passive"
        )
        assert lc.isolation_detected is True
        assert lc.isolation_level == "passive"

    def test_none_isolation_does_not_set_detected(self):
        lc = LLMClassification(domain="logistics", emotional_intensity=0.0, isolation_level="none")
        assert lc.isolation_detected is False

    def test_invalid_isolation_level_normalized_to_none(self):
        lc = LLMClassification(
            domain="logistics", emotional_intensity=0.0, isolation_level="extreme"
        )
        assert lc.isolation_level == "none"
        assert lc.isolation_detected is False

    def test_isolation_detected_explicit_false_overridden_by_active_level(self):
        """isolation_detected should be derived from isolation_level in __post_init__."""
        lc = LLMClassification(
            domain="emotional",
            emotional_intensity=5.0,
            isolation_level="active",
            isolation_detected=False,
        )
        assert lc.isolation_detected is True

    def test_to_dict_includes_isolation_fields(self):
        lc = LLMClassification(
            domain="emotional", emotional_intensity=5.0, isolation_level="passive"
        )
        d = lc.to_dict()
        assert "isolation_level" in d
        assert "isolation_detected" in d
        assert d["isolation_level"] == "passive"
        assert d["isolation_detected"] is True

    def test_from_dict_roundtrip_with_isolation(self):
        original = LLMClassification(
            domain="emotional", emotional_intensity=7.0, isolation_level="active"
        )
        rebuilt = LLMClassification.from_dict(original.to_dict())
        assert rebuilt.isolation_level == "active"
        assert rebuilt.isolation_detected is True
