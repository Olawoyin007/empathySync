"""
Restraint Memory negative invariant (Phase 23.1).

empathySync remembers only what protects the user, never what deepens
engagement. This test makes that guarantee falsifiable: it exercises every
public persistence API, then serializes everything that was written and
asserts that no field outside the allowlist in
scenarios/config/system_defaults.yaml (restraint_memory.allowed_fields)
exists - in particular, no raw conversation content and no derived
preference/persona field.

A PR that persists a new field fails this test until the field is added to
the allowlist - which makes persisting data a conscious, reviewed decision
instead of a side effect. This is a blocking CI gate.
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

ALLOWLIST_PATH = Path(__file__).parent.parent / "scenarios" / "config" / "system_defaults.yaml"

# Maps a top-level key in each JSON file to its allowlist entry.
STRUCTURE_MAP = {
    "wellness_data.json": {
        "_root": "wellness_root",
        "check_ins": "check_ins",
        "usage_sessions": "usage_sessions",
        "policy_events": "policy_events",
        "session_intents": "session_intents",
        "independence_records": "independence_records",
        "handoff_events": "handoff_events",
        "self_reports": "self_reports",
    },
    "trusted_network.json": {
        "_root": "network_root",
        "people": "people",
        "reach_outs": "reach_outs",
        "handoffs": "handoffs",
    },
}


@pytest.fixture(scope="module")
def restraint_config():
    config = yaml.safe_load(open(ALLOWLIST_PATH))["restraint_memory"]
    return config


def _exercise_all_persistence_apis(tmp_path, use_sqlite):
    """Write one representative record through every public persistence API."""
    import utils.database as db_module
    from utils.storage_backend import reset_storage_backend

    db_module._connection = None
    db_module._db_path = None
    reset_storage_backend()

    with (
        patch("utils.wellness_tracker.settings") as tracker_settings,
        patch("utils.trusted_network.settings") as network_settings,
        patch("utils.storage_backend.settings") as backend_settings,
        patch("utils.database.settings") as db_settings,
        patch("config.settings.settings") as core_settings,
    ):
        for mock in (
            tracker_settings,
            network_settings,
            backend_settings,
            db_settings,
            core_settings,
        ):
            mock.DATA_DIR = tmp_path
            mock.USE_SQLITE = use_sqlite
            mock.ENABLE_DEVICE_LOCK = False
            mock.DATA_RETENTION_DAYS = 90
        from utils.wellness_tracker import WellnessTracker
        from utils.trusted_network import TrustedNetwork

        t = WellnessTracker()
        t.add_check_in(4, notes="feeling ok")
        t.add_session(
            duration_minutes=10,
            turn_count=5,
            domains_touched=["logistics"],
            max_risk_weight=2.0,
        )
        t.log_policy_event("crisis_stop", "crisis", 10.0, "Immediate crisis redirect")
        t.record_session_intent("practical", auto_detected=True)
        t.record_task_category("email_drafting")
        t.record_graduation_shown("email_drafting")
        t.record_graduation_dismissal("email_drafting")
        t.record_independence("email_drafting", notes="did it myself")
        t.log_handoff_event(
            "initiated",
            context="after_difficult_task",
            domain="relationships",
            details={"person": "Sam"},
        )
        t.record_self_report("usefulness", "yes", details={"score": 3})

        n = TrustedNetwork()
        n.add_person(
            "Sam",
            relationship="friend",
            contact="sam@example.com",
            notes="old friend",
            domains=["relationships"],
        )
        n.log_reach_out("Sam", method="text", topic="checking in", notes="felt good")
        n.log_handoff_initiated("Sam", "relationships", message_sent="Hey, got a minute?")

    if use_sqlite:
        db_module.close_db()
        db_module._connection = None
        db_module._db_path = None
    reset_storage_backend()


def _walk_forbidden(obj, forbidden, path="root"):
    """Recursively assert no forbidden key name appears anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k.lower() not in forbidden, (
                f"Forbidden field '{k}' persisted at {path} - "
                "conversation content and preference/persona data must never be stored "
                "(restraint_memory invariant, Phase 23.1)"
            )
            _walk_forbidden(v, forbidden, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_forbidden(item, forbidden, f"{path}[{i}]")


class TestRestraintMemoryJSON:
    """The invariant against the JSON backend (default)."""

    @pytest.fixture()
    def data_dir(self, tmp_path):
        _exercise_all_persistence_apis(tmp_path, use_sqlite=False)
        return tmp_path

    def test_every_persisted_field_is_allowlisted(self, data_dir, restraint_config):
        allowed = restraint_config["allowed_fields"]
        checked_records = 0
        for filename, structure in STRUCTURE_MAP.items():
            payload = json.load(open(data_dir / filename))

            root_allowed = set(allowed[structure["_root"]])
            unexpected = set(payload.keys()) - root_allowed
            assert not unexpected, (
                f"{filename} persists top-level fields outside the allowlist: "
                f"{sorted(unexpected)}. Add them to restraint_memory.allowed_fields "
                "only as a conscious, reviewed decision."
            )

            for key, entry_name in structure.items():
                if key == "_root":
                    continue
                for record in payload.get(key, []):
                    unexpected = set(record.keys()) - set(allowed[entry_name])
                    assert not unexpected, (
                        f"{filename}:{key} persists fields outside the allowlist: "
                        f"{sorted(unexpected)}"
                    )
                    checked_records += 1

            # task_patterns is a dict of per-category stats, not a list
            if "task_patterns" in payload:
                for category, stats in payload["task_patterns"].items():
                    unexpected = set(stats.keys()) - set(allowed["task_patterns"])
                    assert not unexpected, (
                        f"task_patterns[{category}] persists fields outside the "
                        f"allowlist: {sorted(unexpected)}"
                    )
                    for use in stats.get("uses", []):
                        unexpected = set(use.keys()) - set(allowed["task_pattern_uses"])
                        assert not unexpected, (
                            f"task_patterns[{category}].uses persists fields outside "
                            f"the allowlist: {sorted(unexpected)}"
                        )
                    checked_records += 1

        assert checked_records >= 10, (
            "The exercise step wrote fewer record types than expected - "
            "if a persistence API was removed, update this test"
        )

    def test_no_forbidden_field_anywhere(self, data_dir, restraint_config):
        """Deny-list scan covers free-form dicts (e.g. handoff details) too."""
        forbidden = {f.lower() for f in restraint_config["forbidden_field_names"]}
        for filename in STRUCTURE_MAP:
            _walk_forbidden(json.load(open(data_dir / filename)), forbidden, filename)


class TestRestraintMemorySQLite:
    """The invariant against the SQLite backend: column names are the schema."""

    @pytest.fixture()
    def db_conn(self, tmp_path):
        _exercise_all_persistence_apis(tmp_path, use_sqlite=True)
        db_files = list(tmp_path.glob("*.db"))
        assert db_files, "SQLite backend did not create a database file"
        conn = sqlite3.connect(db_files[0])
        yield conn
        conn.close()

    def test_every_column_is_allowlisted(self, db_conn, restraint_config):
        allowed_columns = restraint_config["allowed_columns"]
        legacy = restraint_config["legacy_deny_named_columns"]
        forbidden = {f.lower() for f in restraint_config["forbidden_field_names"]}

        tables = [
            r[0]
            for r in db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' " "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        assert tables, "no tables created"
        for table in tables:
            assert table in allowed_columns, (
                f"SQLite table '{table}' is not in restraint_memory.allowed_columns. "
                "Persisting a new table is a conscious, reviewed decision."
            )
            columns = [r[1] for r in db_conn.execute(f"PRAGMA table_info({table})")]
            for column in columns:
                assert column in allowed_columns[table], (
                    f"SQLite table '{table}' column '{column}' is not in the "
                    "restraint_memory allowlist. Persisting a new column is a "
                    "conscious, reviewed decision."
                )
                if column.lower() in forbidden:
                    assert column in legacy.get(table, []), (
                        f"SQLite table '{table}' has forbidden column '{column}' "
                        "that is not a documented legacy exception"
                    )

    def test_user_input_column_is_gone(self, db_conn):
        """The session_intents.user_input column must not exist.

        The write path was removed in Phase 23.1 and the column itself was
        dropped by the schema v3 migration. Its reappearance would mean a
        standing capability to persist raw message text has returned.
        """
        columns = [r[1] for r in db_conn.execute("PRAGMA table_info(session_intents)")]
        assert "user_input" not in columns, (
            "session_intents.user_input exists again - the schema v3 migration "
            "dropped it because raw user input must never be persistable "
            "(restraint_memory invariant)"
        )
