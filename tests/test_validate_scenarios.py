"""
Tests for scripts/validate_scenarios.py

Covers:
- Valid domain files pass without errors
- Missing required fields are caught
- Missing crisis_response / refusal_response are caught
- Malformed triggers (not a list) are caught
- Duplicate triggers across files are caught
- The real scenarios/domains/ directory passes validation
"""

import sys
from pathlib import Path

import pytest
import yaml

# Add scripts/ to path so we can import the validator
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_scenarios import validate_domain_file, find_duplicate_triggers, main


def write_yaml(path, data):
    with open(path, "w") as f:
        yaml.dump(data, f)


VALID_DOMAIN = {
    "domain": "money",
    "risk_weight": 6.0,
    "triggers": ["loan", "debt"],
    "response_rules": ["Keep it brief."],
}


class TestValidateDomainFile:
    def test_valid_file_has_no_errors(self, tmp_path):
        p = tmp_path / "money.yaml"
        write_yaml(p, VALID_DOMAIN)
        assert validate_domain_file(p, VALID_DOMAIN) == []

    def test_missing_domain_field(self, tmp_path):
        data = {k: v for k, v in VALID_DOMAIN.items() if k != "domain"}
        p = tmp_path / "money.yaml"
        errors = validate_domain_file(p, data)
        assert any("domain" in e for e in errors)

    def test_missing_risk_weight(self, tmp_path):
        data = {k: v for k, v in VALID_DOMAIN.items() if k != "risk_weight"}
        p = tmp_path / "money.yaml"
        errors = validate_domain_file(p, data)
        assert any("risk_weight" in e for e in errors)

    def test_missing_triggers(self, tmp_path):
        data = {k: v for k, v in VALID_DOMAIN.items() if k != "triggers"}
        p = tmp_path / "money.yaml"
        errors = validate_domain_file(p, data)
        assert any("triggers" in e for e in errors)

    def test_triggers_not_a_list(self, tmp_path):
        data = {**VALID_DOMAIN, "triggers": "not a list"}
        p = tmp_path / "money.yaml"
        errors = validate_domain_file(p, data)
        assert any("triggers" in e for e in errors)

    def test_missing_response_rules(self, tmp_path):
        data = {k: v for k, v in VALID_DOMAIN.items() if k != "response_rules"}
        p = tmp_path / "money.yaml"
        errors = validate_domain_file(p, data)
        assert any("response_rules" in e for e in errors)

    def test_crisis_requires_crisis_response(self, tmp_path):
        p = tmp_path / "crisis.yaml"
        errors = validate_domain_file(p, VALID_DOMAIN)
        assert any("crisis_response" in e for e in errors)

    def test_crisis_passes_with_crisis_response(self, tmp_path):
        data = {**VALID_DOMAIN, "crisis_response": "Call 999."}
        p = tmp_path / "crisis.yaml"
        assert validate_domain_file(p, data) == []

    def test_harmful_requires_refusal_response(self, tmp_path):
        p = tmp_path / "harmful.yaml"
        errors = validate_domain_file(p, VALID_DOMAIN)
        assert any("refusal_response" in e for e in errors)

    def test_harmful_passes_with_refusal_response(self, tmp_path):
        data = {**VALID_DOMAIN, "refusal_response": "No."}
        p = tmp_path / "harmful.yaml"
        assert validate_domain_file(p, data) == []


class TestFindDuplicateTriggers:
    def test_no_duplicates(self, tmp_path):
        files = [
            (tmp_path / "a.yaml", {"triggers": ["loan", "debt"]}),
            (tmp_path / "b.yaml", {"triggers": ["sad", "anxious"]}),
        ]
        assert find_duplicate_triggers(files) == []

    def test_duplicate_detected(self, tmp_path):
        files = [
            (tmp_path / "a.yaml", {"triggers": ["loan", "debt"]}),
            (tmp_path / "b.yaml", {"triggers": ["debt", "anxious"]}),
        ]
        errors = find_duplicate_triggers(files)
        assert len(errors) == 1
        assert "debt" in errors[0]
        assert "a.yaml" in errors[0]
        assert "b.yaml" in errors[0]

    def test_case_insensitive(self, tmp_path):
        files = [
            (tmp_path / "a.yaml", {"triggers": ["Loan"]}),
            (tmp_path / "b.yaml", {"triggers": ["loan"]}),
        ]
        errors = find_duplicate_triggers(files)
        assert len(errors) == 1

    def test_missing_triggers_key_ignored(self, tmp_path):
        files = [
            (tmp_path / "a.yaml", {}),
            (tmp_path / "b.yaml", {"triggers": ["loan"]}),
        ]
        assert find_duplicate_triggers(files) == []


class TestMainAgainstRealScenarios:
    def test_real_domains_pass_validation(self):
        domains_dir = Path(__file__).parent.parent / "scenarios" / "domains"
        result = main(domains_dir)
        assert result == 0, "Real scenarios/domains/ failed validation - fix the YAML files"

    def test_missing_directory_returns_error(self, tmp_path):
        result = main(tmp_path / "nonexistent")
        assert result == 1

    def test_empty_directory_returns_error(self, tmp_path):
        result = main(tmp_path)
        assert result == 1
