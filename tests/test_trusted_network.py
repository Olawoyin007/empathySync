"""
Tests for src/utils/trusted_network.py

Covers:
- Person management (add, get, update, remove)
- Reach-out tracking and metrics
- Prompt generation from scenario loader
- Connection building features (Phase 12)
- Context-aware handoff (Phase 5)
- Error handling and data recovery
- Connection health metrics
"""

import json
import pytest
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_mock_loader():
    """Build a scenario loader mock with sane defaults for all methods."""
    loader = MagicMock()

    # Prompt methods return nested dicts matching YAML structure
    loader.get_all_prompts.return_value = {
        "human_connection": {
            "trusted_network_prompts": {
                "initial_setup": ["Who are your people?"],
                "reflection": ["When did you last talk to someone?"],
                "prompts_by_domain": {
                    "money": ["Who do you talk to about money?"],
                    "general": ["Who could you talk to about this?"],
                },
            },
            "reach_out_templates": {
                "need_to_talk": {
                    "name": "Need to talk",
                    "templates": ["Hey, can we talk?"],
                },
                "checking_in": {
                    "name": "Checking in",
                    "templates": ["Just checking in on you!"],
                },
            },
            "exit_celebrations": {
                "chose_human": ["Great choice reaching out!"],
                "ending_session": ["See you next time."],
            },
        }
    }

    # Connection building methods
    loader.get_general_signposts.return_value = [
        {"category": "community_groups", "description": "Join a group"}
    ]
    loader.get_signpost_reflection_prompt.return_value = "What interests you?"
    loader.get_signpost_encouragement.return_value = "You've got this."
    loader.get_domain_signposts.return_value = [
        {"category": "support_groups", "description": "Find support"}
    ]
    loader.get_all_first_contact_situations.return_value = [
        {"situation": "at_a_meetup", "tips": ["Introduce yourself"]}
    ]
    loader.get_first_contact_situation.return_value = {
        "situation": "at_a_meetup",
        "tips": ["Introduce yourself"],
    }
    loader.get_first_contact_principles.return_value = ["Be genuine"]
    loader.get_first_contact_affirmation.return_value = "It's okay to be nervous."

    # Handoff methods
    loader.detect_handoff_context.return_value = "after_difficult_task"
    loader.get_handoff_intro_prompts.return_value = ["It might help to talk to someone."]
    loader.get_handoff_messages.return_value = ["I'm going through something."]
    loader.get_handoff_follow_up_prompts.return_value = ["Did you reach out?"]
    loader.get_handoff_settings.return_value = {
        "follow_up_delay_hours": 24,
        "max_follow_ups_per_week": 2,
    }
    loader.get_handoff_celebrations.return_value = ["You reached out!"]

    return loader


@pytest.fixture
def mock_loader():
    return _make_mock_loader()


@pytest.fixture
def network(tmp_path, mock_loader):
    """Create a TrustedNetwork with mocked settings and scenario loader."""
    with (
        patch("utils.trusted_network.settings") as mock_settings,
        patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
    ):
        mock_settings.DATA_DIR = tmp_path
        mock_settings.USE_SQLITE = False

        from utils.trusted_network import TrustedNetwork

        tn = TrustedNetwork()
        yield tn


# ==================== PERSON MANAGEMENT ====================


class TestPersonManagement:
    """Tests for add/get/update/remove people."""

    def test_add_person_returns_dict(self, network):
        person = network.add_person("Alice", relationship="friend")
        assert person["name"] == "Alice"
        assert person["relationship"] == "friend"
        assert "id" in person
        assert "added_at" in person

    def test_add_person_increments_id(self, network):
        p1 = network.add_person("Alice")
        p2 = network.add_person("Bob")
        assert p2["id"] == p1["id"] + 1

    def test_add_person_with_domains(self, network):
        person = network.add_person("Alice", domains=["money", "health"])
        assert person["domains"] == ["money", "health"]

    def test_add_person_default_domains_empty(self, network):
        person = network.add_person("Alice")
        assert person["domains"] == []

    def test_get_all_people_empty(self, network):
        assert network.get_all_people() == []

    def test_get_all_people_returns_added(self, network):
        network.add_person("Alice")
        network.add_person("Bob")
        network.add_person("Charlie")
        assert len(network.get_all_people()) == 3

    def test_get_person_by_name_exact(self, network):
        network.add_person("Alice Smith")
        found = network.get_person_by_name("Alice Smith")
        assert found is not None
        assert found["name"] == "Alice Smith"

    def test_get_person_by_name_case_insensitive(self, network):
        network.add_person("Alice")
        found = network.get_person_by_name("alice")
        assert found is not None
        assert found["name"] == "Alice"

    def test_get_person_by_name_partial_match(self, network):
        network.add_person("Alice Smith")
        found = network.get_person_by_name("Alice")
        assert found is not None

    def test_get_person_by_name_not_found(self, network):
        network.add_person("Alice")
        assert network.get_person_by_name("Bob") is None

    def test_get_people_for_domain_filters(self, network):
        network.add_person("Alice", domains=["money"])
        network.add_person("Bob", domains=["health"])
        matches = network.get_people_for_domain("money")
        assert len(matches) == 1
        assert matches[0]["name"] == "Alice"

    def test_get_people_for_domain_no_match_returns_all(self, network):
        network.add_person("Alice", domains=["money"])
        network.add_person("Bob", domains=["health"])
        matches = network.get_people_for_domain("spirituality")
        assert len(matches) == 2  # Falls back to all people

    def test_update_person(self, network):
        person = network.add_person("Alice")
        updated = network.update_person(person["id"], {"relationship": "sister"})
        assert updated is not None
        assert updated["relationship"] == "sister"

    def test_update_person_persists(self, network):
        person = network.add_person("Alice")
        network.update_person(person["id"], {"notes": "Best friend"})
        reloaded = network.get_person_by_name("Alice")
        assert reloaded["notes"] == "Best friend"

    def test_update_person_not_found(self, network):
        assert network.update_person(999, {"name": "Ghost"}) is None

    def test_remove_person(self, network):
        person = network.add_person("Alice")
        assert network.remove_person(person["id"]) is True
        assert network.get_all_people() == []

    def test_remove_person_not_found(self, network):
        assert network.remove_person(999) is False

    def test_clear_data(self, network):
        network.add_person("Alice")
        network.add_person("Bob")
        network.clear_data()
        assert network.get_all_people() == []


# ==================== REACH-OUTS ====================


class TestReachOuts:
    """Tests for reach-out tracking."""

    def test_log_reach_out_returns_dict(self, network):
        network.add_person("Alice")
        reach_out = network.log_reach_out("Alice", method="call", topic="money")
        assert reach_out["person_name"] == "Alice"
        assert reach_out["method"] == "call"
        assert "date" in reach_out

    def test_log_reach_out_updates_last_contact(self, network):
        network.add_person("Alice")
        network.log_reach_out("Alice", method="text")
        person = network.get_person_by_name("Alice")
        assert person["last_contact"] == date.today().isoformat()

    def test_get_recent_reach_outs(self, network):
        network.add_person("Alice")
        network.log_reach_out("Alice", method="call")
        recent = network.get_recent_reach_outs(days=7)
        assert len(recent) == 1

    def test_count_reach_outs_this_week(self, network):
        network.add_person("Alice")
        network.log_reach_out("Alice")
        network.log_reach_out("Alice")
        assert network.count_reach_outs_this_week() == 2

    def test_get_neglected_contacts_no_contact(self, network):
        network.add_person("Alice")  # last_contact is None
        neglected = network.get_neglected_contacts(days=30)
        assert len(neglected) == 1
        assert neglected[0]["name"] == "Alice"

    def test_get_neglected_contacts_recent_not_neglected(self, network):
        network.add_person("Alice")
        network.log_reach_out("Alice")  # Sets last_contact to today
        neglected = network.get_neglected_contacts(days=30)
        assert len(neglected) == 0


# ==================== PROMPTS ====================


class TestPrompts:
    """Tests for prompt generation from scenario loader."""

    def test_get_setup_prompt(self, network):
        prompt = network.get_setup_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_setup_prompt_fallback(self, network, mock_loader):
        mock_loader.get_all_prompts.return_value = {}
        prompt = network.get_setup_prompt()
        assert "people" in prompt.lower() or "who" in prompt.lower()

    def test_get_reflection_prompt(self, network):
        prompt = network.get_reflection_prompt()
        assert isinstance(prompt, str)

    def test_get_domain_prompt(self, network):
        prompt = network.get_domain_prompt("money")
        assert isinstance(prompt, str)

    def test_get_reach_out_template(self, network):
        template = network.get_reach_out_template("need_to_talk")
        assert "name" in template
        assert "template" in template

    def test_get_reach_out_template_fallback(self, network, mock_loader):
        mock_loader.get_all_prompts.return_value = {}
        template = network.get_reach_out_template("unknown_situation")
        assert "template" in template  # Should have fallback

    def test_get_exit_celebration_chose_human(self, network):
        msg = network.get_exit_celebration(chose_human=True)
        assert isinstance(msg, str)

    def test_get_exit_celebration_ending_session(self, network):
        msg = network.get_exit_celebration(chose_human=False)
        assert isinstance(msg, str)

    def test_suggest_person_for_domain(self, network):
        network.add_person("Alice", domains=["money"])
        person = network.suggest_person_for_domain("money")
        assert person is not None
        assert person["name"] == "Alice"

    def test_suggest_person_for_domain_none(self, network):
        # No people in network
        assert network.suggest_person_for_domain("money") is None


# ==================== CONNECTION BUILDING ====================


class TestConnectionBuilding:
    """Tests for Phase 12 connection building features."""

    def test_is_network_empty_true(self, network):
        assert network.is_network_empty() is True

    def test_is_network_empty_false(self, network):
        network.add_person("Alice")
        assert network.is_network_empty() is False

    def test_get_signposts_structure(self, network):
        result = network.get_signposts()
        assert "general_signposts" in result
        assert "reflection_prompt" in result
        assert "encouragement" in result

    def test_get_signposts_with_domain(self, network):
        result = network.get_signposts(domain="health")
        assert "domain_signposts" in result
        assert result["domain"] == "health"

    def test_get_signposts_skips_logistics_domain(self, network):
        result = network.get_signposts(domain="logistics")
        assert "domain_signposts" not in result

    def test_get_first_contact_templates_all(self, network):
        result = network.get_first_contact_templates()
        assert "situations" in result
        assert "principles" in result
        assert "affirmation" in result

    def test_get_first_contact_templates_specific(self, network, mock_loader):
        result = network.get_first_contact_templates(situation="at_a_meetup")
        mock_loader.get_first_contact_situation.assert_called_with("at_a_meetup")

    def test_get_building_network_content(self, network):
        result = network.get_building_network_content()
        assert "signposts" in result
        assert "first_contact" in result
        assert "setup_prompt" in result
        assert "is_empty" in result


# ==================== HANDOFF ====================


class TestHandoff:
    """Tests for context-aware handoff (Phase 5)."""

    def test_get_contextual_handoff_structure(self, network):
        result = network.get_contextual_handoff(
            emotional_weight="high_weight",
            domain="relationships",
        )
        assert "context" in result
        assert "intro_prompt" in result
        assert "message_template" in result
        assert "follow_up_prompt" in result

    def test_log_handoff_initiated(self, network):
        handoff = network.log_handoff_initiated(
            context="after_difficult_task",
            domain="relationships",
            person_name="Alice",
        )
        assert handoff["context"] == "after_difficult_task"
        assert handoff["person_name"] == "Alice"
        assert handoff["status"] == "initiated"
        assert "id" in handoff

    def test_record_handoff_outcome_reached_out(self, network):
        handoff = network.log_handoff_initiated("test", person_name="Alice")
        network.add_person("Alice")  # Needed for reach_out logging
        result = network.record_handoff_outcome(
            handoff["id"], reached_out=True, outcome="very_helpful"
        )
        assert result is not None
        assert result["status"] == "completed"
        assert result["reached_out"] is True
        assert result["outcome"] == "very_helpful"

    def test_record_handoff_outcome_not_reached_out(self, network):
        handoff = network.log_handoff_initiated("test")
        result = network.record_handoff_outcome(handoff["id"], reached_out=False)
        assert result["reached_out"] is False
        assert result["status"] == "completed"

    def test_record_handoff_outcome_not_found(self, network):
        assert network.record_handoff_outcome(999, reached_out=True) is None

    def test_mark_follow_up_shown(self, network):
        handoff = network.log_handoff_initiated("test")
        network.mark_follow_up_shown(handoff["id"])
        data = network._load_data()
        h = [h for h in data.get("handoffs", []) if h["id"] == handoff["id"]][0]
        assert h["follow_up_shown"] is True

    def test_get_handoff_stats_empty(self, network):
        stats = network.get_handoff_stats()
        assert stats["total_initiated"] == 0
        assert stats["reach_out_rate"] == 0

    def test_get_handoff_stats_with_data(self, network):
        network.add_person("Alice")
        h1 = network.log_handoff_initiated("test", person_name="Alice")
        network.record_handoff_outcome(h1["id"], reached_out=True, outcome="very_helpful")
        h2 = network.log_handoff_initiated("test2")
        network.record_handoff_outcome(h2["id"], reached_out=False)

        stats = network.get_handoff_stats()
        assert stats["total_initiated"] == 2
        assert stats["total_reached_out"] == 1
        assert stats["reach_out_rate"] == 0.5

    def test_get_handoff_celebration(self, network):
        msg = network.get_handoff_celebration("reached_out")
        assert isinstance(msg, str)


# ==================== HEALTH METRICS ====================


class TestConnectionHealth:
    """Tests for connection health metrics."""

    def test_empty_network_health(self, network):
        health = network.get_connection_health()
        assert health["total_trusted_people"] == 0
        assert health["network_configured"] is False
        assert health["is_reaching_out"] is False

    def test_active_network_health(self, network):
        network.add_person("Alice")
        network.add_person("Bob")
        network.log_reach_out("Alice")

        health = network.get_connection_health()
        assert health["total_trusted_people"] == 2
        assert health["network_configured"] is True
        assert health["reach_outs_this_week"] == 1
        assert health["is_reaching_out"] is True


# ==================== ERROR HANDLING ====================


class TestErrorHandling:
    """Tests for data recovery and error handling."""

    def test_corrupted_json_recovers(self, tmp_path, mock_loader):
        """Loading corrupted JSON should return defaults, not crash."""
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            # Write corrupted JSON before creating TrustedNetwork
            data_file = tmp_path / "trusted_network.json"
            data_file.write_text("{invalid json!!!")

            from utils.trusted_network import TrustedNetwork

            tn = TrustedNetwork()

            # Should have recovered with defaults
            assert tn.get_all_people() == []

    def test_backup_corrupted_file_created(self, tmp_path, mock_loader):
        """Corrupted file should be backed up when data is loaded."""
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            data_file = tmp_path / "trusted_network.json"
            data_file.write_text("{bad json")

            from utils.trusted_network import TrustedNetwork

            tn = TrustedNetwork()
            # Trigger _load_data() which detects corruption and creates backup
            tn.get_all_people()

            # Check backup file was created (pattern: trusted_network.corrupted.TIMESTAMP.json)
            backups = list(tmp_path.glob("trusted_network.corrupted.*.json"))
            assert len(backups) == 1

    def test_schema_migration_v0_to_current(self, tmp_path, mock_loader):
        """Data without schema_version should be migrated to the current version."""
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            # Write v0 data (no schema_version)
            data_file = tmp_path / "trusted_network.json"
            data_file.write_text(
                json.dumps(
                    {
                        "people": [{"id": 1, "name": "Alice"}],
                        "reach_outs": [],
                    }
                )
            )

            from utils.trusted_network import TrustedNetwork

            tn = TrustedNetwork()

            # Data should be migrated
            data = tn._load_data()
            # Assert against the constant, not a literal - this test was pinned to
            # 1 and went stale the moment a v2 existed.
            from utils.trusted_network import SCHEMA_VERSION

            assert data["schema_version"] == SCHEMA_VERSION
            assert len(data["people"]) == 1

    def test_schema_migration_v1_to_v2_strips_message_preview(self, tmp_path, mock_loader):
        """A stored outreach message must be removed from existing files (#186).

        message_preview held the first 100 characters of a message the user
        actually sent to a person. Dropping it from the write path only helps new
        records; Phase 23.3 will render what is stored back to the user, so files
        that already contain it have to be cleaned on load too.
        """
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            data_file = tmp_path / "trusted_network.json"
            data_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "people": [],
                        "reach_outs": [],
                        "handoffs": [
                            {
                                "id": 1,
                                "person_name": "Sam",
                                "message_preview": "Hey, got a minute? I've had a rough week",
                                "status": "initiated",
                            }
                        ],
                    }
                )
            )

            from utils.trusted_network import SCHEMA_VERSION, TrustedNetwork

            data = TrustedNetwork()._load_data()

            assert "message_preview" not in data["handoffs"][0]
            assert data["handoffs"][0]["person_name"] == "Sam"
            assert data["handoffs"][0]["status"] == "initiated"
            assert data["schema_version"] == SCHEMA_VERSION

            # and it is gone from the file on disk, not just the loaded copy
            assert "message_preview" not in data_file.read_text()

    def test_new_handoff_stores_no_message_content(self, tmp_path, mock_loader):
        """The outreach text is not accepted or stored at all (#186)."""
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            from utils.trusted_network import TrustedNetwork

            handoff = TrustedNetwork().log_handoff_initiated("general", person_name="Sam")
            assert "message_preview" not in handoff

    def test_data_persists_across_reloads(self, tmp_path, mock_loader):
        """Data saved by one instance should be readable by another."""
        with (
            patch("utils.trusted_network.settings") as mock_settings,
            patch("utils.trusted_network.get_scenario_loader", return_value=mock_loader),
        ):
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = False

            from utils.trusted_network import TrustedNetwork

            tn1 = TrustedNetwork()
            tn1.add_person("Alice", relationship="friend")

            tn2 = TrustedNetwork()
            people = tn2.get_all_people()
            assert len(people) == 1
            assert people[0]["name"] == "Alice"
