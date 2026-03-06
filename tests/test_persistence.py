"""
Tests for Phase 11: Persistence Hardening & Multi-Device Sync

Tests cover:
- SQLite database operations (database.py)
- Lock file mechanism (lockfile.py)
- Storage backend abstraction (storage_backend.py)
"""

import pytest
import json
import os
import sys
import tempfile
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ==================== DATABASE TESTS ====================


class TestDatabaseModule:
    """Tests for src/utils/database.py"""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory and patch settings."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("utils.database.settings") as mock_settings:
            mock_settings.DATA_DIR = data_dir
            yield data_dir

    @pytest.fixture
    def db_connection(self, temp_data_dir):
        """Get a test database connection."""
        # Need to reset module state for each test
        import utils.database as db_module

        db_module._connection = None
        db_module._db_path = None

        with patch("utils.database.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir

            conn = db_module.get_db()
            yield conn

            db_module.close_db()

    def test_get_db_creates_database(self, temp_data_dir):
        """Test that get_db creates the database file."""
        import utils.database as db_module

        db_module._connection = None
        db_module._db_path = None

        with patch("utils.database.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir

            conn = db_module.get_db()

            db_path = temp_data_dir / "empathySync.db"
            assert db_path.exists()

            db_module.close_db()

    def test_get_db_creates_schema(self, db_connection, temp_data_dir):
        """Test that get_db creates all required tables."""
        cursor = db_connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "schema_info",
            "check_ins",
            "usage_sessions",
            "policy_events",
            "session_intents",
            "independence_records",
            "handoff_events",
            "self_reports",
            "task_patterns",
            "trusted_people",
            "reach_outs",
        }

        assert expected_tables.issubset(tables)

    def test_schema_version_recorded(self, db_connection):
        """Test that schema version is recorded."""
        cursor = db_connection.execute("SELECT MAX(version) FROM schema_info")
        version = cursor.fetchone()[0]

        assert version >= 1

    def test_checkpoint_for_sync(self, temp_data_dir):
        """Test that checkpoint consolidates WAL."""
        import utils.database as db_module

        db_module._connection = None
        db_module._db_path = None

        with patch("utils.database.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir

            conn = db_module.get_db()

            # Insert some data to ensure WAL has content
            conn.execute("INSERT INTO check_ins (feeling_score, notes) VALUES (3, 'test')")
            conn.commit()

            # Run checkpoint
            result = db_module.checkpoint_for_sync()
            assert result is True

            db_module.close_db()

    def test_insert_and_query_check_in(self, db_connection):
        """Test inserting and querying a check-in."""
        cursor = db_connection.execute(
            "INSERT INTO check_ins (feeling_score, notes) VALUES (?, ?)", (4, "Feeling good today")
        )
        db_connection.commit()

        row_id = cursor.lastrowid
        assert row_id is not None

        cursor = db_connection.execute("SELECT * FROM check_ins WHERE id = ?", (row_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["feeling_score"] == 4
        assert row["notes"] == "Feeling good today"

    def test_insert_usage_session(self, db_connection):
        """Test inserting a usage session with JSON domains."""
        domains = ["money", "relationships"]

        cursor = db_connection.execute(
            """INSERT INTO usage_sessions
               (duration_minutes, turn_count, domains_touched, max_risk_weight)
               VALUES (?, ?, ?, ?)""",
            (15, 8, json.dumps(domains), 5.0),
        )
        db_connection.commit()

        cursor = db_connection.execute(
            "SELECT * FROM usage_sessions WHERE id = ?", (cursor.lastrowid,)
        )
        row = cursor.fetchone()

        assert row["duration_minutes"] == 15
        assert row["turn_count"] == 8
        assert json.loads(row["domains_touched"]) == domains
        assert row["max_risk_weight"] == 5.0

    def test_transaction_rollback(self, db_connection):
        """Test that transaction context manager rolls back on error."""
        from utils.database import transaction

        initial_count = db_connection.execute("SELECT COUNT(*) FROM check_ins").fetchone()[0]

        try:
            with transaction() as conn:
                conn.execute("INSERT INTO check_ins (feeling_score) VALUES (?)", (3,))
                # Force an error
                raise ValueError("Test error")
        except ValueError:
            pass

        final_count = db_connection.execute("SELECT COUNT(*) FROM check_ins").fetchone()[0]

        assert final_count == initial_count  # Rollback should have occurred


# ==================== LOCK FILE TESTS ====================


class TestLockFileModule:
    """Tests for src/utils/lockfile.py"""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory and patch settings."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = data_dir
            yield data_dir

    @pytest.fixture
    def clean_lock_state(self, temp_data_dir):
        """Reset lock module state before each test."""
        import utils.lockfile as lock_module

        # Reset global state
        lock_module._device_id = None
        lock_module._heartbeat_thread = None
        lock_module._heartbeat_stop.clear()

        # Clean up any existing lock file
        lock_path = temp_data_dir / ".empathySync.lock"
        if lock_path.exists():
            lock_path.unlink()

        yield

        # Cleanup after test
        lock_module._heartbeat_stop.set()
        if lock_module._heartbeat_thread:
            lock_module._heartbeat_thread.join(timeout=1.0)
            lock_module._heartbeat_thread = None

    def test_get_device_id_consistent(self, temp_data_dir, clean_lock_state):
        """Test that device ID is consistent across calls."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            id1 = lock_module.get_device_id()
            id2 = lock_module.get_device_id()

            assert id1 == id2
            assert len(id1) > 0

    def test_acquire_lock_creates_file(self, temp_data_dir, clean_lock_state):
        """Test that acquire_lock creates the lock file."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            result = lock_module.acquire_lock()
            assert result is True

            lock_path = temp_data_dir / ".empathySync.lock"
            assert lock_path.exists()

            lock_module.release_lock()

    def test_acquire_lock_content(self, temp_data_dir, clean_lock_state):
        """Test that lock file contains required fields."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            lock_module.acquire_lock()

            lock_path = temp_data_dir / ".empathySync.lock"
            with open(lock_path) as f:
                data = json.load(f)

            assert "device_id" in data
            assert "hostname" in data
            assert "pid" in data
            assert "started_at" in data
            assert "heartbeat" in data

            lock_module.release_lock()

    def test_check_lock_status_no_lock(self, temp_data_dir, clean_lock_state):
        """Test check_lock_status when no lock exists."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            status = lock_module.check_lock_status()

            assert status["locked"] is False
            assert status["locked_by_us"] is False
            assert status["locked_by_other"] is False

    def test_check_lock_status_our_lock(self, temp_data_dir, clean_lock_state):
        """Test check_lock_status when we hold the lock."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            lock_module.acquire_lock()
            status = lock_module.check_lock_status()

            assert status["locked"] is True
            assert status["locked_by_us"] is True
            assert status["locked_by_other"] is False

            lock_module.release_lock()

    def test_check_lock_status_stale_lock(self, temp_data_dir, clean_lock_state):
        """Test that stale locks are detected."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            # Create a stale lock file (heartbeat too old)
            lock_path = temp_data_dir / ".empathySync.lock"
            old_time = (datetime.now() - timedelta(minutes=10)).isoformat()

            lock_data = {
                "device_id": "other-device-123",
                "hostname": "other-host",
                "pid": 99999,
                "started_at": old_time,
                "heartbeat": old_time,
            }

            with open(lock_path, "w") as f:
                json.dump(lock_data, f)

            status = lock_module.check_lock_status()

            # Stale lock should not be considered "locked"
            assert status["stale"] is True
            assert status["locked"] is False

    def test_release_lock_removes_file(self, temp_data_dir, clean_lock_state):
        """Test that release_lock removes the lock file."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            lock_module.acquire_lock()
            lock_path = temp_data_dir / ".empathySync.lock"
            assert lock_path.exists()

            lock_module.release_lock()
            assert not lock_path.exists()

    def test_force_acquire_takes_over(self, temp_data_dir, clean_lock_state):
        """Test that force=True can take over another device's lock."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            # Create a lock from "another device"
            lock_path = temp_data_dir / ".empathySync.lock"
            now = datetime.now().isoformat()

            lock_data = {
                "device_id": "other-device-123",
                "hostname": "other-host",
                "pid": 99999,
                "started_at": now,
                "heartbeat": now,
            }

            with open(lock_path, "w") as f:
                json.dump(lock_data, f)

            # Try to acquire without force (should fail)
            result = lock_module.acquire_lock(force=False)
            assert result is False

            # Try to acquire with force (should succeed)
            result = lock_module.acquire_lock(force=True)
            assert result is True

            # Verify we now hold the lock
            status = lock_module.check_lock_status()
            assert status["locked_by_us"] is True

            lock_module.release_lock()

    def test_format_lock_warning(self, temp_data_dir, clean_lock_state):
        """Test that format_lock_warning generates user-friendly message."""
        import utils.lockfile as lock_module

        with patch("utils.lockfile.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.LOCK_STALE_TIMEOUT = 300

            status = {
                "locked_by_other": True,
                "hostname": "my-macbook",
                "started_at": datetime.now().isoformat(),
                "age_seconds": 120,
            }

            warning = lock_module.format_lock_warning(status)

            assert "my-macbook" in warning
            assert "Take Over" in warning

    def test_format_lock_warning_no_warning_needed(self, temp_data_dir, clean_lock_state):
        """Test that format_lock_warning returns empty when no warning needed."""
        import utils.lockfile as lock_module

        status = {"locked_by_other": False}
        warning = lock_module.format_lock_warning(status)

        assert warning == ""


# ==================== STORAGE BACKEND TESTS ====================


class TestStorageBackend:
    """Tests for src/utils/storage_backend.py"""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        return data_dir

    @pytest.fixture
    def json_backend(self, temp_data_dir):
        """Get a JSON backend instance."""
        from utils.storage_backend import JSONBackend, reset_storage_backend

        reset_storage_backend()

        with patch("utils.storage_backend.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.USE_SQLITE = False

            backend = JSONBackend()
            yield backend

            backend.close()

    @pytest.fixture
    def sqlite_backend(self, temp_data_dir):
        """Get a SQLite backend instance."""
        from utils.storage_backend import SQLiteBackend, reset_storage_backend

        reset_storage_backend()

        # Also patch the database module settings
        with (
            patch("utils.storage_backend.settings") as mock_settings,
            patch("utils.database.settings") as db_settings,
        ):
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.USE_SQLITE = True
            db_settings.DATA_DIR = temp_data_dir

            backend = SQLiteBackend()
            yield backend

            backend.close()

    # ==================== JSON Backend Tests ====================

    def test_json_add_check_in(self, json_backend, temp_data_dir):
        """Test adding check-in via JSON backend."""
        result = json_backend.add_check_in(4, "Test notes")

        assert result["feeling_score"] == 4
        assert result["notes"] == "Test notes"
        assert "id" in result

        # Verify persistence
        wellness_file = temp_data_dir / "wellness_data.json"
        with open(wellness_file) as f:
            data = json.load(f)

        assert len(data["check_ins"]) == 1
        assert data["check_ins"][0]["feeling_score"] == 4

    def test_json_get_recent_check_ins(self, json_backend):
        """Test getting recent check-ins."""
        # Add some check-ins
        json_backend.add_check_in(3, "Day 1")
        json_backend.add_check_in(4, "Day 2")
        json_backend.add_check_in(5, "Day 3")

        recent = json_backend.get_recent_check_ins(days=7)

        assert len(recent) == 3

    def test_json_add_trusted_person(self, json_backend, temp_data_dir):
        """Test adding trusted person via JSON backend."""
        result = json_backend.add_trusted_person(
            name="Mom",
            relationship="parent",
            contact="555-1234",
            domains=["relationships", "money"],
        )

        assert result["name"] == "Mom"
        assert result["relationship"] == "parent"
        assert "money" in result["domains"]

        # Verify persistence
        network_file = temp_data_dir / "trusted_network.json"
        with open(network_file) as f:
            data = json.load(f)

        assert len(data["people"]) == 1
        assert data["people"][0]["name"] == "Mom"

    def test_json_add_session(self, json_backend):
        """Test adding usage session."""
        result = json_backend.add_session(
            duration_minutes=15,
            turn_count=8,
            domains_touched=["money", "health"],
            max_risk_weight=6.0,
        )

        assert result["duration_minutes"] == 15
        assert result["turn_count"] == 8
        assert "money" in result["domains_touched"]

    def test_json_add_policy_event(self, json_backend):
        """Test adding policy event."""
        result = json_backend.add_policy_event(
            event_type="domain_redirect",
            domain="crisis",
            action_taken="Redirected to 988",
            risk_weight=10.0,
        )

        assert result["event_type"] == "domain_redirect"
        assert result["domain"] == "crisis"

    def test_json_clear_all_data(self, json_backend, temp_data_dir):
        """Test clearing all data."""
        # Add some data
        json_backend.add_check_in(4, "Test")
        json_backend.add_trusted_person("Test Person")

        # Clear
        json_backend.clear_all_data()

        # Verify empty
        assert len(json_backend.get_recent_check_ins()) == 0
        assert len(json_backend.get_all_trusted_people()) == 0

    # ==================== SQLite Backend Tests ====================

    def test_sqlite_add_check_in(self, sqlite_backend):
        """Test adding check-in via SQLite backend."""
        result = sqlite_backend.add_check_in(4, "Test notes")

        assert result["feeling_score"] == 4
        assert result["notes"] == "Test notes"
        assert "id" in result

    def test_sqlite_get_recent_check_ins(self, sqlite_backend):
        """Test getting recent check-ins from SQLite."""
        # Add some check-ins
        sqlite_backend.add_check_in(3, "Day 1")
        sqlite_backend.add_check_in(4, "Day 2")
        sqlite_backend.add_check_in(5, "Day 3")

        recent = sqlite_backend.get_recent_check_ins(days=7)

        assert len(recent) == 3

    def test_sqlite_add_trusted_person(self, sqlite_backend):
        """Test adding trusted person via SQLite backend."""
        result = sqlite_backend.add_trusted_person(
            name="Mom",
            relationship="parent",
            contact="555-1234",
            domains=["relationships", "money"],
        )

        assert result["name"] == "Mom"
        assert result["relationship"] == "parent"
        assert "money" in result["domains"]

    def test_sqlite_get_all_trusted_people(self, sqlite_backend):
        """Test getting all trusted people from SQLite."""
        sqlite_backend.add_trusted_person("Person 1")
        sqlite_backend.add_trusted_person("Person 2")

        people = sqlite_backend.get_all_trusted_people()

        assert len(people) == 2

    def test_sqlite_add_session(self, sqlite_backend):
        """Test adding usage session to SQLite."""
        result = sqlite_backend.add_session(
            duration_minutes=15,
            turn_count=8,
            domains_touched=["money", "health"],
            max_risk_weight=6.0,
        )

        assert result["duration_minutes"] == 15
        assert result["turn_count"] == 8

    def test_sqlite_task_patterns(self, sqlite_backend):
        """Test task pattern recording and retrieval."""
        # Record pattern multiple times
        sqlite_backend.record_task_pattern("email_drafting")
        sqlite_backend.record_task_pattern("email_drafting")
        sqlite_backend.record_task_pattern("code_help")

        stats = sqlite_backend.get_task_pattern_stats("email_drafting")

        assert stats is not None
        assert stats["count"] == 2

        all_patterns = sqlite_backend.get_all_task_patterns()
        assert "email_drafting" in all_patterns
        assert "code_help" in all_patterns

    def test_sqlite_remove_trusted_person(self, sqlite_backend):
        """Test removing trusted person from SQLite."""
        person = sqlite_backend.add_trusted_person("To Remove")
        person_id = person["id"]

        result = sqlite_backend.remove_trusted_person(person_id)
        assert result is True

        people = sqlite_backend.get_all_trusted_people()
        assert len(people) == 0

    def test_sqlite_update_trusted_person(self, sqlite_backend):
        """Test updating trusted person in SQLite."""
        person = sqlite_backend.add_trusted_person("Original Name")
        person_id = person["id"]

        updated = sqlite_backend.update_trusted_person(
            person_id, {"name": "Updated Name", "relationship": "friend"}
        )

        assert updated["name"] == "Updated Name"
        assert updated["relationship"] == "friend"

    def test_sqlite_cascade_delete_reach_outs(self, sqlite_backend):
        """Test that deleting a person cascades to their reach_outs."""
        # Add a trusted person
        person = sqlite_backend.add_trusted_person("Test Person", relationship="friend")
        person_id = person["id"]

        # Add reach-outs for this person using the backend's method
        sqlite_backend.add_reach_out(person_id, method="phone", notes="Called them")
        sqlite_backend.add_reach_out(person_id, method="text", notes="Texted them")

        # Verify reach-outs exist via direct query
        from utils.database import get_db

        db = get_db()
        cursor = db.execute("SELECT COUNT(*) FROM reach_outs WHERE person_id = ?", (person_id,))
        count_before = cursor.fetchone()[0]
        assert count_before == 2, "Should have 2 reach-outs before delete"

        # Delete the person
        sqlite_backend.remove_trusted_person(person_id)

        # Verify reach-outs were cascade deleted (no orphans)
        cursor = db.execute("SELECT COUNT(*) FROM reach_outs WHERE person_id = ?", (person_id,))
        count_after = cursor.fetchone()[0]

        assert count_after == 0, "Reach-outs should be cascade deleted when person is removed"


# ==================== INTEGRATION TESTS ====================


class TestStorageIntegration:
    """Integration tests for storage with trackers."""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        return data_dir

    def test_wellness_tracker_with_json(self, temp_data_dir):
        """Test WellnessTracker with JSON backend."""
        from utils.wellness_tracker import WellnessTracker

        with (
            patch("config.settings.settings") as mock_settings,
            patch("utils.wellness_tracker.settings") as tracker_settings,
        ):
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.USE_SQLITE = False
            tracker_settings.DATA_DIR = temp_data_dir
            tracker_settings.USE_SQLITE = False

            tracker = WellnessTracker()

            # Test basic operations
            check_in = tracker.add_check_in(4, "Test")
            assert check_in["feeling_score"] == 4

            session = tracker.add_session(10, turn_count=5)
            assert session["duration_minutes"] == 10

    def test_trusted_network_with_json(self, temp_data_dir):
        """Test TrustedNetwork with JSON backend."""
        from utils.trusted_network import TrustedNetwork
        from utils.scenario_loader import get_scenario_loader

        with (
            patch("config.settings.settings") as mock_settings,
            patch("utils.trusted_network.settings") as network_settings,
        ):
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.USE_SQLITE = False
            network_settings.DATA_DIR = temp_data_dir
            network_settings.USE_SQLITE = False

            network = TrustedNetwork()

            # Test basic operations
            person = network.add_person("Test Person", relationship="friend")
            assert person["name"] == "Test Person"

            people = network.get_all_people()
            assert len(people) == 1


# ==================== WRITE GATE TESTS ====================


class TestWriteGate:
    """Tests for src/utils/write_gate.py"""

    def test_write_allowed_by_default(self):
        """Test that writes are allowed by default."""
        from utils.write_gate import is_write_allowed, set_read_only

        # Reset to default state
        set_read_only(False)

        assert is_write_allowed() is True

    def test_set_read_only_blocks_writes(self):
        """Test that setting read-only mode blocks writes."""
        from utils.write_gate import is_write_allowed, set_read_only, is_read_only

        set_read_only(True)
        assert is_write_allowed() is False
        assert is_read_only() is True

        # Reset
        set_read_only(False)
        assert is_write_allowed() is True

    def test_check_write_permission_raises(self):
        """Test that check_write_permission raises in read-only mode."""
        from utils.write_gate import check_write_permission, set_read_only, WriteBlockedError

        set_read_only(True)

        with pytest.raises(WriteBlockedError):
            check_write_permission()

        # Reset
        set_read_only(False)

    def test_storage_backend_respects_write_gate(self, tmp_path):
        """Test that storage backends block writes in read-only mode."""
        from utils.storage_backend import JSONBackend, reset_storage_backend
        from utils.write_gate import set_read_only, WriteBlockedError

        reset_storage_backend()

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("utils.storage_backend.settings") as mock_settings:
            mock_settings.DATA_DIR = data_dir
            mock_settings.USE_SQLITE = False

            backend = JSONBackend()

            # Enable read-only mode
            set_read_only(True)

            # Attempts to write should raise
            with pytest.raises(WriteBlockedError):
                backend.add_check_in(4, "Test")

            with pytest.raises(WriteBlockedError):
                backend.add_trusted_person("Test Person")

            # Reset and verify writes work again
            set_read_only(False)
            result = backend.add_check_in(4, "Now it works")
            assert result["feeling_score"] == 4

            backend.close()


class TestDataPruning:
    """Tests for data pruning / active forgetting."""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        return data_dir

    @pytest.fixture
    def json_backend(self, temp_data_dir):
        from utils.storage_backend import JSONBackend, reset_storage_backend

        reset_storage_backend()
        with patch("utils.storage_backend.settings") as mock_settings:
            mock_settings.DATA_DIR = temp_data_dir
            mock_settings.USE_SQLITE = False
            backend = JSONBackend()
            yield backend
            backend.close()

    def _inject_old_records(self, backend, days_ago):
        """Add records with dates in the past."""
        old_date = (date.today() - timedelta(days=days_ago)).isoformat()
        data = backend._load_wellness()
        data["check_ins"].append(
            {"id": 99, "date": old_date, "datetime": old_date, "feeling_score": 3, "notes": "old"}
        )
        data["usage_sessions"].append(
            {
                "id": 99,
                "date": old_date,
                "datetime": old_date,
                "hour": 10,
                "duration_minutes": 15,
                "turn_count": 5,
                "domains_touched": [],
                "max_risk_weight": 1.0,
            }
        )
        data["policy_events"].append(
            {
                "id": 99,
                "date": old_date,
                "datetime": old_date,
                "policy_type": "test",
                "domain": "logistics",
                "risk_weight": 1.0,
                "action_taken": "none",
            }
        )
        backend._save_wellness(data)

    def test_prune_removes_old_records(self, json_backend):
        """Records older than retention_days are pruned."""
        # Add a current record
        json_backend.add_check_in(4, "recent")
        # Add records from 100 days ago
        self._inject_old_records(json_backend, days_ago=100)

        pruned = json_backend.prune_old_data(retention_days=90)

        assert pruned == 3  # 1 check-in + 1 session + 1 policy event
        # Recent check-in should survive
        data = json_backend._load_wellness()
        assert len(data["check_ins"]) == 1
        assert data["check_ins"][0]["notes"] == "recent"

    def test_prune_keeps_recent_records(self, json_backend):
        """Records within retention window are kept."""
        json_backend.add_check_in(4, "today")
        self._inject_old_records(json_backend, days_ago=30)

        pruned = json_backend.prune_old_data(retention_days=90)

        assert pruned == 0
        data = json_backend._load_wellness()
        assert len(data["check_ins"]) == 2

    def test_prune_returns_zero_when_no_old_data(self, json_backend):
        """No pruning needed when all data is recent."""
        json_backend.add_check_in(5, "fresh")

        pruned = json_backend.prune_old_data(retention_days=90)

        assert pruned == 0

    def test_prune_does_not_save_when_nothing_pruned(self, json_backend):
        """File is not rewritten when no records are pruned."""
        json_backend.add_check_in(5, "fresh")
        with patch.object(json_backend, "_save_wellness") as mock_save:
            json_backend.prune_old_data(retention_days=90)
            mock_save.assert_not_called()

    def test_prune_respects_write_gate(self, json_backend):
        """Pruning is blocked when in read-only mode."""
        from utils.write_gate import set_read_only, WriteBlockedError

        set_read_only(True)
        try:
            with pytest.raises(WriteBlockedError):
                json_backend.prune_old_data(retention_days=90)
        finally:
            set_read_only(False)


class TestMaintenanceMode:
    """Tests for empathysync --maintenance CLI flag."""

    def test_maintenance_flag_calls_run_maintenance(self):
        """--maintenance flag routes to run_maintenance."""
        with patch("src.cli.run_maintenance") as mock:
            with patch("sys.argv", ["empathysync", "--maintenance"]):
                from src.cli import main

                main()
            assert mock.called

    def test_maintenance_and_mode_prefers_maintenance(self):
        """--maintenance takes priority over --mode."""
        with patch("src.cli.run_maintenance") as mock_maint:
            with patch("src.cli.run_cli") as mock_cli:
                with patch("sys.argv", ["empathysync", "--maintenance", "--mode", "cli"]):
                    from src.cli import main

                    main()
                assert mock_maint.called
                assert not mock_cli.called

    def test_run_maintenance_completes(self, tmp_path):
        """run_maintenance runs without error on empty data."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with (
            patch("config.settings.settings") as mock_settings,
            patch("utils.storage_backend.settings") as mock_sb_settings,
        ):
            mock_settings.DATA_RETENTION_DAYS = 90
            mock_settings.DATA_DIR = data_dir
            mock_settings.USE_SQLITE = False
            mock_settings.OLLAMA_MODEL = "test-model"
            mock_settings.OLLAMA_HOST = "http://localhost:11434"
            mock_sb_settings.DATA_DIR = data_dir
            mock_sb_settings.USE_SQLITE = False

            from utils.storage_backend import reset_storage_backend

            reset_storage_backend()

            from src.cli import run_maintenance

            # Should complete without raising
            run_maintenance()

    def test_run_maintenance_prune_disabled(self, tmp_path, capsys):
        """Maintenance reports pruning disabled when DATA_RETENTION_DAYS=0."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with (
            patch("config.settings.settings") as mock_settings,
            patch("utils.storage_backend.settings") as mock_sb_settings,
        ):
            mock_settings.DATA_RETENTION_DAYS = 0
            mock_settings.DATA_DIR = data_dir
            mock_settings.USE_SQLITE = False
            mock_settings.OLLAMA_MODEL = "test"
            mock_settings.OLLAMA_HOST = "http://localhost:11434"
            mock_sb_settings.DATA_DIR = data_dir
            mock_sb_settings.USE_SQLITE = False

            from utils.storage_backend import reset_storage_backend

            reset_storage_backend()

            from src.cli import run_maintenance

            run_maintenance()

        output = capsys.readouterr().out
        assert "disabled" in output.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
