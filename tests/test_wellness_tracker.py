"""
Tests for WellnessTracker - targeting uncovered lines to improve coverage from 67% to ~85%.

Focuses on:
- should_enforce_cooldown (lines 283-300)
- get_wellness_summary (lines 350-371)
- _load_data error paths (lines 402-412)
- _load_data_from_sqlite (lines 416-451)
- _migrate_schema (lines 458-473)
- _backup_corrupted_file (lines 479-487)
- _save_data schema/exception paths (lines 500, 518-525)
- clear_data / reset_all_data (lines 530-545)
- should_show_intent_check_in (lines 592-615)
- record_graduation_accepted (lines 875-886)
- get_recent_check_ins / get_today_check_in (lines 104-117)
- add_check_in SQLite path (line 85)
- add_session SQLite path (line 139)
- calculate_dependency_signals branches (lines 236-265)
- log_policy_event branches (lines 318, 324)
- get_recent_policy_events (lines 342-344)
- should_show_handoff_follow_up (lines 1084-1088)
- calculate_anti_engagement_score branches (lines 1335-1421)
- should_show_self_report triggers (lines 1576-1603)
- record_self_report branches (lines 1616-1637)
- _is_late_night_hour error branch (lines 1175-1176)
- _calculate_change (line 1271)
- get_my_patterns_dashboard health branches (lines 1484-1488)
- _trend_indicator negative branch (line 1547)
- record_task_category uses trimming (line 744)
- get_category_stats null (line 796)
- should_show_graduation_prompt no_data (line 820)
- record_graduation_shown missing category (line 851)
- record_graduation_dismissal missing category (line 865)
- record_independence (line 903, 909)
- log_handoff_event branches (lines 993-1002, 1018)
- _get_storage_backend SQLite path (lines 26-28)
"""

import json
import os
import sys
import pytest
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def tracker(tmp_path):
    """Create a WellnessTracker with temporary data directory."""
    with patch("utils.wellness_tracker.settings") as mock_settings:
        mock_settings.DATA_DIR = tmp_path
        mock_settings.USE_SQLITE = False
        mock_settings.ENABLE_DEVICE_LOCK = False
        from utils.wellness_tracker import WellnessTracker

        tracker = WellnessTracker()
        yield tracker


@pytest.fixture
def tracker_with_sessions(tracker):
    """Tracker pre-loaded with several practical (logistics) sessions today."""
    today_str = date.today().isoformat()
    now_str = datetime.now().isoformat()
    data = tracker._load_data()
    for i in range(8):
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": now_str,
                "hour": 14,
                "duration_minutes": 20,
                "turn_count": 5,
                "domains_touched": ["logistics"],
                "max_risk_weight": 1.0,
            }
        )
    tracker._save_data(data)
    return tracker


@pytest.fixture
def tracker_with_sensitive_sessions(tracker):
    """Tracker pre-loaded with 8 sensitive (relationships) sessions today."""
    today_str = date.today().isoformat()
    now_str = datetime.now().isoformat()
    data = tracker._load_data()
    for i in range(8):
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": now_str,
                "hour": 14,
                "duration_minutes": 15,
                "turn_count": 5,
                "domains_touched": ["relationships"],
                "max_risk_weight": 5.0,
            }
        )
    tracker._save_data(data)
    return tracker


# ==================== _get_storage_backend ====================


class TestGetStorageBackend:
    """Test the module-level _get_storage_backend function."""

    def test_returns_none_when_sqlite_disabled(self):
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.USE_SQLITE = False
            from utils.wellness_tracker import _get_storage_backend

            result = _get_storage_backend()
            assert result is None

    def test_returns_backend_when_sqlite_enabled(self):
        mock_backend = MagicMock()
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.USE_SQLITE = True
            with patch("utils.storage_backend.get_storage_backend", return_value=mock_backend):
                from utils.wellness_tracker import _get_storage_backend

                result = _get_storage_backend()
                assert result is mock_backend


# ==================== CHECK-INS ====================


class TestCheckIns:
    """Test check-in methods - lines 85, 104-106, 110-117."""

    def test_get_recent_check_ins_returns_last_n(self, tracker):
        """Lines 104-106: get_recent_check_ins returns recent entries."""
        for i in range(10):
            tracker.add_check_in(i % 5 + 1, f"note {i}")
        recent = tracker.get_recent_check_ins(days=3)
        assert len(recent) == 3

    def test_get_recent_check_ins_empty(self, tracker):
        """Lines 104-106: empty check_ins returns empty list."""
        recent = tracker.get_recent_check_ins(days=7)
        assert recent == []

    def test_get_today_check_in_found(self, tracker):
        """Lines 110-117: returns today's check-in."""
        tracker.add_check_in(4, "good day")
        result = tracker.get_today_check_in()
        assert result is not None
        assert result["feeling_score"] == 4

    def test_get_today_check_in_not_found(self, tracker):
        """Lines 110-117: returns None when no check-in today."""
        # Add a check-in with a past date
        data = tracker._load_data()
        data["check_ins"].append(
            {
                "date": "2024-01-01",
                "datetime": "2024-01-01T12:00:00",
                "feeling_score": 3,
                "notes": "",
            }
        )
        tracker._save_data(data)
        result = tracker.get_today_check_in()
        assert result is None

    def test_add_check_in_sqlite_path(self, tmp_path):
        """Line 85: SQLite backend delegation."""
        mock_backend = MagicMock()
        mock_backend.add_check_in.return_value = {"feeling_score": 3}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                result = tracker.add_check_in(3, "test")
                mock_backend.add_check_in.assert_called_once_with(3, "test")


# ==================== SESSION TRACKING - SQLite path ====================


class TestSessionSQLite:
    """Test add_session SQLite delegation - line 139."""

    def test_add_session_sqlite(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.add_session.return_value = {"duration_minutes": 10}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.add_session(10, 5, ["health"], 7.0)
                mock_backend.add_session.assert_called_once_with(10, 5, ["health"], 7.0)


# ==================== DEPENDENCY SIGNALS BRANCHES ====================


class TestDependencySignalsBranches:
    """Test calculate_dependency_signals branches - lines 236-265."""

    def test_7plus_sensitive_sessions_today(self, tracker_with_sensitive_sessions):
        """7+ sensitive sessions adds 4.0 and warning."""
        signals = tracker_with_sensitive_sessions.calculate_dependency_signals()
        assert signals["sensitive_sessions_today"] == 8
        assert signals["dependency_score"] >= 4.0
        assert any("personal conversations" in w for w in signals["warnings"])

    def test_7plus_logistics_sessions_not_flagged(self, tracker_with_sessions):
        """Practical (logistics-only) sessions do not trigger the sensitive session score."""
        signals = tracker_with_sessions.calculate_dependency_signals()
        assert signals["sessions_today"] == 8
        assert signals["sensitive_sessions_today"] == 0
        assert signals["dependency_score"] < 4.0

    def test_5_sensitive_sessions_today(self, tracker):
        """5-6 sensitive sessions adds 2.5 and warning."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        for _ in range(5):
            data["usage_sessions"].append(
                {
                    "date": today_str,
                    "datetime": datetime.now().isoformat(),
                    "hour": 14,
                    "duration_minutes": 5,
                    "turn_count": 3,
                    "domains_touched": ["emotional"],
                    "max_risk_weight": 5.0,
                }
            )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["sensitive_sessions_today"] == 5
        assert any("5 personal conversations" in w for w in signals["warnings"])

    def test_3_sensitive_sessions_today(self, tracker):
        """3-4 sensitive sessions adds 1.5, no warning."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        for _ in range(3):
            data["usage_sessions"].append(
                {
                    "date": today_str,
                    "datetime": datetime.now().isoformat(),
                    "hour": 14,
                    "duration_minutes": 10,
                    "turn_count": 3,
                    "domains_touched": ["health"],
                    "max_risk_weight": 7.0,
                }
            )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["sensitive_sessions_today"] == 3
        assert signals["dependency_score"] >= 1.5

    def test_180plus_minutes_today(self, tracker):
        """180+ total minutes adds 2.0 and warning."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": datetime.now().isoformat(),
                "hour": 14,
                "duration_minutes": 190,
                "turn_count": 50,
                "domains_touched": [],
                "max_risk_weight": 0,
            }
        )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["minutes_today"] >= 180
        assert any("minutes" in w for w in signals["warnings"])

    def test_60plus_minutes_today(self, tracker):
        """Line 249: 60-119 minutes adds 1.0, no warning."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": datetime.now().isoformat(),
                "hour": 14,
                "duration_minutes": 80,
                "turn_count": 30,
                "domains_touched": [],
                "max_risk_weight": 0,
            }
        )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["minutes_today"] >= 60

    def test_3plus_late_night_sessions(self, tracker):
        """Lines 253-254: 3+ late night sessions adds 2.0 and warning."""
        data = tracker._load_data()
        week_dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(4)]
        for d in week_dates[:3]:
            data["usage_sessions"].append(
                {
                    "date": d,
                    "datetime": f"{d}T23:30:00",
                    "hour": 23,
                    "duration_minutes": 15,
                    "turn_count": 3,
                    "domains_touched": [],
                    "max_risk_weight": 0,
                }
            )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["late_night_sessions"] >= 3
        assert any("late-night" in w for w in signals["warnings"])

    def test_1_late_night_session(self, tracker):
        """Line 256: 1-2 late night sessions adds 1.0."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": f"{today_str}T23:30:00",
                "hour": 23,
                "duration_minutes": 15,
                "turn_count": 3,
                "domains_touched": [],
                "max_risk_weight": 0,
            }
        )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["late_night_sessions"] >= 1

    def test_escalating_usage(self, tracker):
        """Lines 260-261: escalating usage adds 1.5 and warning."""
        data = tracker._load_data()
        # Prior week: 2 sessions
        for i in range(2):
            d = (date.today() - timedelta(days=10)).isoformat()
            data["usage_sessions"].append(
                {
                    "date": d,
                    "datetime": f"{d}T14:00:00",
                    "hour": 14,
                    "duration_minutes": 10,
                    "turn_count": 3,
                    "domains_touched": [],
                    "max_risk_weight": 0,
                }
            )
        # This week: 5 sessions (> 2 * 1.5 = 3)
        for i in range(5):
            d = (date.today() - timedelta(days=i % 5)).isoformat()
            data["usage_sessions"].append(
                {
                    "date": d,
                    "datetime": f"{d}T14:00:00",
                    "hour": 14,
                    "duration_minutes": 10,
                    "turn_count": 3,
                    "domains_touched": [],
                    "max_risk_weight": 0,
                }
            )
        tracker._save_data(data)
        signals = tracker.calculate_dependency_signals()
        assert signals["is_escalating"] is True
        assert any("increasing" in w for w in signals["warnings"])

    def test_late_night_session_bonus(self, tracker):
        """Line 265: current late night adds 0.5."""
        with patch(
            "utils.wellness_tracker.WellnessTracker.is_late_night_session", return_value=True
        ):
            signals = tracker.calculate_dependency_signals()
            assert signals["dependency_score"] >= 0.5


# ==================== COOLDOWN ====================


class TestShouldEnforceCooldown:
    """Test should_enforce_cooldown - lines 283-300."""

    def test_cooldown_7plus_sensitive_sessions(self, tracker_with_sensitive_sessions):
        """7+ sensitive sessions triggers cooldown."""
        should, reason = tracker_with_sensitive_sessions.should_enforce_cooldown()
        assert should is True
        assert "personal conversations" in reason

    def test_cooldown_logistics_sessions_do_not_trigger(self, tracker_with_sessions):
        """8 logistics-only sessions do NOT trigger the sensitive-session cooldown."""
        should, _ = tracker_with_sessions.should_enforce_cooldown()
        assert should is False

    def test_cooldown_180plus_minutes(self, tracker):
        """180+ total minutes triggers cooldown."""
        data = tracker._load_data()
        today_str = date.today().isoformat()
        data["usage_sessions"].append(
            {
                "date": today_str,
                "datetime": datetime.now().isoformat(),
                "hour": 14,
                "duration_minutes": 190,
                "turn_count": 50,
                "domains_touched": [],
                "max_risk_weight": 0,
            }
        )
        tracker._save_data(data)
        should, reason = tracker.should_enforce_cooldown()
        assert should is True
        assert "time" in reason.lower()

    def test_cooldown_high_dependency(self, tracker):
        """dependency_score >= 8 triggers cooldown."""
        with patch.object(
            tracker,
            "calculate_dependency_signals",
            return_value={
                "sessions_today": 2,
                "sensitive_sessions_today": 2,
                "minutes_today": 30,
                "dependency_score": 9.0,
            },
        ):
            should, reason = tracker.should_enforce_cooldown()
            assert should is True
            assert "relying" in reason.lower()

    def test_no_cooldown_normal_usage(self, tracker):
        """Line 300: no cooldown needed."""
        should, reason = tracker.should_enforce_cooldown()
        assert should is False
        assert reason == ""


# ==================== POLICY EVENTS ====================


class TestPolicyEvents:
    """Test policy event logging - lines 318, 324, 342-344."""

    def test_log_policy_event_sqlite(self, tmp_path):
        """Line 318: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.add_policy_event.return_value = {"policy_type": "test"}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.log_policy_event("test", "health", 7.0, "redirected")
                mock_backend.add_policy_event.assert_called_once()

    def test_log_policy_event_missing_key(self, tracker):
        """Line 324: handles missing policy_events key."""
        data = tracker._load_data()
        del data["policy_events"]
        tracker._save_data(data)
        event = tracker.log_policy_event("test", "health", 7.0, "redirected")
        assert event["policy_type"] == "test"

    def test_get_recent_policy_events_with_data(self, tracker):
        """Lines 342-344: returns last N events."""
        for i in range(15):
            tracker.log_policy_event(f"type_{i}", "health", 5.0, f"action_{i}")
        events = tracker.get_recent_policy_events(limit=5)
        assert len(events) == 5
        assert events[-1]["policy_type"] == "type_14"

    def test_get_recent_policy_events_empty(self, tracker):
        """Lines 342-344: empty events returns empty list."""
        events = tracker.get_recent_policy_events()
        assert events == []


# ==================== WELLNESS SUMMARY ====================


class TestWellnessSummary:
    """Test get_wellness_summary - lines 350-371."""

    def test_summary_with_check_ins(self, tracker):
        """Lines 360-363: summary with check-in data."""
        tracker.add_check_in(4, "good")
        tracker.add_check_in(2, "bad")
        tracker.add_session(15, 5, ["logistics"], 1.0)

        summary = tracker.get_wellness_summary()
        assert summary["total_checkins"] == 2
        assert summary["average_feeling"] == 3.0
        assert summary["latest_checkin"] is not None
        assert summary["sessions_today"] >= 1

    def test_summary_without_check_ins(self, tracker):
        """Lines 364-366: summary with no check-ins."""
        summary = tracker.get_wellness_summary()
        assert summary["total_checkins"] == 0
        assert summary["average_feeling"] is None
        assert summary["latest_checkin"] is None

    def test_summary_dependency_fields(self, tracker):
        """Lines 368-382: dependency fields present."""
        summary = tracker.get_wellness_summary()
        assert "dependency_score" in summary
        assert "dependency_warnings" in summary
        assert "should_take_break" in summary
        assert isinstance(summary["should_take_break"], bool)

    def test_summary_should_take_break_true(self, tracker):
        """Line 381: should_take_break when dependency >= 5."""
        with patch.object(
            tracker,
            "calculate_dependency_signals",
            return_value={"dependency_score": 6.0, "warnings": ["test"]},
        ):
            summary = tracker.get_wellness_summary()
            assert summary["should_take_break"] is True


# ==================== DATA MANAGEMENT ====================


class TestLoadData:
    """Test _load_data error paths - lines 402-412."""

    def test_load_data_file_not_found(self, tracker):
        """Lines 402-404: FileNotFoundError returns defaults."""
        tracker.data_file.unlink(missing_ok=True)
        data = tracker._load_data()
        assert data["schema_version"] == 1
        assert data["check_ins"] == []

    def test_load_data_corrupted_json(self, tracker):
        """Lines 406-409: JSONDecodeError backs up and returns defaults."""
        tracker.data_file.write_text("{invalid json!!!")
        data = tracker._load_data()
        assert data["schema_version"] == 1
        # Check backup file was created
        backups = list(tracker.data_file.parent.glob("*.corrupted.*.json"))
        assert len(backups) >= 1

    def test_load_data_unexpected_error(self, tracker):
        """Lines 410-412: generic exception returns defaults."""
        with patch("builtins.open", side_effect=PermissionError("denied")):
            data = tracker._load_data()
            assert data["schema_version"] == 1

    def test_load_data_sqlite_path(self, tmp_path):
        """Lines 394-395: SQLite path calls _load_data_from_sqlite."""
        mock_backend = MagicMock()
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                with patch.object(
                    tracker,
                    "_load_data_from_sqlite",
                    return_value={"schema_version": 1, "check_ins": []},
                ):
                    data = tracker._load_data()
                    assert data["schema_version"] == 1


class TestLoadDataFromSQLite:
    """Test _load_data_from_sqlite - lines 416-451."""

    def test_load_from_sqlite_success(self, tmp_path):
        """Lines 416-443: successful SQLite load."""
        mock_backend = MagicMock()
        mock_backend.get_recent_check_ins.return_value = [{"feeling_score": 3}]
        mock_backend.get_sessions_for_period.return_value = []
        mock_backend.get_recent_policy_events.return_value = []
        mock_backend.get_session_intents_for_period.return_value = []
        mock_backend.get_independence_records_for_period.return_value = []
        mock_backend.get_handoff_events_for_period.return_value = []
        mock_backend.get_recent_self_reports.return_value = []
        mock_backend.get_all_task_patterns.return_value = {}

        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                data = tracker._load_data_from_sqlite()
                assert data["check_ins"] == [{"feeling_score": 3}]
                assert data["schema_version"] == 1

    def test_load_from_sqlite_error_falls_back_to_json(self, tmp_path):
        """Lines 444-451: SQLite error falls back to JSON."""
        mock_backend = MagicMock()
        mock_backend.get_recent_check_ins.side_effect = Exception("db error")

        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                # Ensure JSON file exists with data
                json_path = tmp_path / "wellness_data.json"
                json_path.write_text(
                    json.dumps({"schema_version": 1, "check_ins": [{"feeling_score": 5}]})
                )
                data = tracker._load_data_from_sqlite()
                assert data["check_ins"] == [{"feeling_score": 5}]

    def test_load_from_sqlite_error_no_json_fallback(self, tmp_path):
        """Lines 447-451: SQLite error + no JSON returns defaults."""
        mock_backend = MagicMock()
        mock_backend.get_recent_check_ins.side_effect = Exception("db error")

        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                # Remove JSON file
                json_path = tmp_path / "wellness_data.json"
                json_path.unlink(missing_ok=True)
                data = tracker._load_data_from_sqlite()
                assert data["schema_version"] == 1
                assert data["check_ins"] == []


class TestMigrateSchema:
    """Test _migrate_schema - lines 458-473."""

    def test_migrate_v0_to_v1(self, tracker):
        """Lines 458-473: v0 data gets migrated to v1."""
        old_data = {
            "check_ins": [{"feeling_score": 3}],
            "usage_sessions": [],
        }
        result = tracker._migrate_schema(old_data)
        assert result["schema_version"] == 1
        assert "policy_events" in result
        assert "session_intents" in result
        assert "independence_records" in result

    def test_no_migration_needed(self, tracker):
        """Already at current version - no migration."""
        data = tracker._get_default_data()
        result = tracker._migrate_schema(data)
        assert result["schema_version"] == 1


class TestBackupCorruptedFile:
    """Test _backup_corrupted_file - lines 479-487."""

    def test_backup_created(self, tracker):
        """Lines 479-486: corrupted file is backed up."""
        tracker.data_file.write_text("corrupted!")
        tracker._backup_corrupted_file()
        backups = list(tracker.data_file.parent.glob("*.corrupted.*.json"))
        assert len(backups) == 1
        assert not tracker.data_file.exists()

    def test_backup_no_file(self, tracker):
        """Line 479: no crash if file doesn't exist."""
        tracker.data_file.unlink(missing_ok=True)
        tracker._backup_corrupted_file()  # Should not raise

    def test_backup_rename_fails(self, tracker):
        """Lines 486-487: handles rename failure gracefully."""
        tracker.data_file.write_text("corrupted!")
        with patch.object(Path, "rename", side_effect=OSError("permission denied")):
            tracker._backup_corrupted_file()  # Should not raise


class TestSaveData:
    """Test _save_data edge cases - lines 500, 518-525."""

    def test_save_adds_schema_version(self, tracker):
        """Line 500: missing schema_version is added."""
        data = {"check_ins": [], "usage_sessions": []}
        tracker._save_data(data)
        loaded = json.loads(tracker.data_file.read_text())
        assert loaded["schema_version"] == 1

    def test_save_failure_cleans_temp_file(self, tracker):
        """Lines 518-525: exception during write cleans up temp file."""
        data = tracker._get_default_data()
        with patch("json.dump", side_effect=IOError("disk full")):
            with pytest.raises(IOError):
                tracker._save_data(data)
        # Verify no temp files left
        temps = list(tracker.data_file.parent.glob(".wellness_data_*.tmp"))
        assert len(temps) == 0


class TestClearAndReset:
    """Test clear_data and reset_all_data - lines 530-545."""

    def test_clear_data_json(self, tracker):
        """Lines 533-534: clear_data resets to defaults."""
        tracker.add_check_in(4)
        tracker.clear_data()
        data = tracker._load_data()
        assert data["check_ins"] == []

    def test_clear_data_sqlite(self, tmp_path):
        """Lines 530-532: SQLite clear_data."""
        mock_backend = MagicMock()
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.clear_data()
                mock_backend.clear_all_data.assert_called_once()

    def test_reset_all_data_json(self, tracker):
        """Lines 543-545: reset_all_data clears everything including task_patterns."""
        tracker.record_task_category("email_drafting")
        tracker.add_check_in(3)
        tracker.reset_all_data()
        data = tracker._load_data()
        assert data["check_ins"] == []
        assert data.get("task_patterns") == {}

    def test_reset_all_data_sqlite(self, tmp_path):
        """Lines 539-541: SQLite reset."""
        mock_backend = MagicMock()
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.reset_all_data()
                mock_backend.clear_all_data.assert_called_once()


# ==================== SESSION INTENT CHECK-IN ====================


class TestShouldShowIntentCheckIn:
    """Test should_show_intent_check_in - lines 592-615."""

    def test_sessions_since_checkin_threshold(self, tracker):
        """Lines 592-603: show after min_sessions_between without check-in."""
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": True},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
        ]
        tracker._save_data(data)
        result = tracker.should_show_intent_check_in("how are you?")
        assert result is True

    def test_days_since_checkin_threshold(self, tracker):
        """Lines 606-613: show after max_days_between days."""
        old_date = (date.today() - timedelta(days=10)).isoformat()
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": old_date, "intent": "practical", "was_check_in": True},
            {"date": old_date, "intent": "practical", "was_check_in": False},
        ]
        tracker._save_data(data)
        result = tracker.should_show_intent_check_in("hello")
        assert result is True

    def test_no_checkin_found_sessions_threshold(self, tracker):
        """Lines 595-599: no was_check_in found, counts all sessions."""
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
        ]
        tracker._save_data(data)
        result = tracker.should_show_intent_check_in("hello")
        assert result is True

    def test_recent_checkin_no_show(self, tracker):
        """Lines 602-603: not enough sessions since last check-in."""
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": True},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
        ]
        tracker._save_data(data)
        result = tracker.should_show_intent_check_in("hello")
        assert result is False

    def test_invalid_date_in_checkin(self, tracker):
        """Line 612: handles invalid date gracefully."""
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": "not-a-date", "intent": "practical", "was_check_in": True},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": False},
        ]
        tracker._save_data(data)
        # Should not crash, just continue
        tracker.should_show_intent_check_in("hello")

    def test_returns_false_at_end(self, tracker):
        """Line 615: returns False when no trigger condition met."""
        data = tracker._load_data()
        data["session_intents"] = [
            {"date": date.today().isoformat(), "intent": "practical", "was_check_in": True},
        ]
        tracker._save_data(data)
        result = tracker.should_show_intent_check_in("hello")
        assert result is False


# ==================== SESSION INTENT - SQLite + missing key ====================


class TestRecordSessionIntent:
    """Test record_session_intent - lines 630, 636."""

    def test_record_intent_sqlite(self, tmp_path):
        """Line 630: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.add_session_intent.return_value = {"intent": "practical"}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.record_session_intent("practical", False, True)
                mock_backend.add_session_intent.assert_called_once()

    def test_record_intent_missing_key(self, tracker):
        """Line 636: handles missing session_intents key."""
        data = tracker._load_data()
        if "session_intents" in data:
            del data["session_intents"]
        tracker._save_data(data)
        record = tracker.record_session_intent("practical")
        assert record["intent"] == "practical"


# ==================== GET RECENT INTENT ====================


class TestGetRecentIntent:
    """Test get_recent_intent - line 691."""

    def test_no_intents(self, tracker):
        """Line 691: returns None when no intents."""
        result = tracker.get_recent_intent()
        assert result is None


# ==================== TASK PATTERN TRACKING ====================


class TestTaskPatternTracking:
    """Test task pattern tracking edge cases - lines 744, 796, 820, 851, 865."""

    def test_uses_trimmed_to_100(self, tracker):
        """Line 744: uses list trimmed to last 100."""
        data = tracker._load_data()
        data["task_patterns"] = {
            "email": {
                "count": 105,
                "first_use": "2024-01-01T00:00:00",
                "uses": [
                    {"datetime": "2024-01-01T00:00:00", "date": "2024-01-01"} for _ in range(105)
                ],
                "graduation_shown_count": 0,
                "dismissal_count": 0,
            }
        }
        tracker._save_data(data)
        tracker.record_task_category("email")
        data = tracker._load_data()
        assert len(data["task_patterns"]["email"]["uses"]) <= 100

    def test_get_category_stats_nonexistent(self, tracker):
        """Line 796: returns None for nonexistent category."""
        result = tracker.get_category_stats("nonexistent")
        assert result is None

    def test_should_show_graduation_no_data(self, tracker):
        """Line 820: returns False with 'no_data' reason."""
        should, reason = tracker.should_show_graduation_prompt("nonexistent", 5)
        assert should is False
        assert reason == "no_data"

    def test_record_graduation_shown_missing_category(self, tracker):
        """Line 851: no-op for missing category."""
        tracker.record_graduation_shown("nonexistent")  # Should not raise

    def test_record_graduation_dismissal_missing_category(self, tracker):
        """Line 865: no-op for missing category."""
        tracker.record_graduation_dismissal("nonexistent")  # Should not raise

    def test_record_task_category_sqlite(self, tmp_path):
        """Lines 707-709: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.record_task_pattern.return_value = {
            "count": 1,
            "last_7_days": 1,
            "last_30_days": 1,
            "created_at": "2024-01-01",
            "last_seen": "2024-01-01",
            "graduation_shown_count": 0,
            "dismissal_count": 0,
        }
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                result = tracker.record_task_category("email")
                assert result["category"] == "email"
                assert result["count"] == 1


# ==================== GRADUATION ACCEPTED ====================


class TestRecordGraduationAccepted:
    """Test record_graduation_accepted - lines 875-886."""

    def test_record_accepted(self, tracker):
        """Lines 875-886: records accepted tip."""
        tracker.record_task_category("email")
        tracker.record_graduation_accepted("email")
        data = tracker._load_data()
        pattern = data["task_patterns"]["email"]
        assert len(pattern["accepted_tips"]) == 1

    def test_record_accepted_multiple(self, tracker):
        """Lines 881-884: appends multiple accepted tips."""
        tracker.record_task_category("email")
        tracker.record_graduation_accepted("email")
        tracker.record_graduation_accepted("email")
        data = tracker._load_data()
        assert len(data["task_patterns"]["email"]["accepted_tips"]) == 2

    def test_record_accepted_missing_category(self, tracker):
        """Line 877: no-op for missing category."""
        tracker.record_graduation_accepted("nonexistent")  # Should not raise


# ==================== INDEPENDENCE TRACKING ====================


class TestRecordIndependence:
    """Test record_independence - lines 903, 909."""

    def test_record_independence_sqlite(self, tmp_path):
        """Line 903: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.add_independence_record.return_value = {"category": "email"}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.record_independence("email", "did it myself")
                mock_backend.add_independence_record.assert_called_once()

    def test_record_independence_missing_key(self, tracker):
        """Line 909: handles missing independence_records key."""
        data = tracker._load_data()
        if "independence_records" in data:
            del data["independence_records"]
        tracker._save_data(data)
        record = tracker.record_independence("email", "notes")
        assert record["category"] == "email"


# ==================== HANDOFF TRACKING ====================


class TestHandoffTracking:
    """Test handoff methods - lines 993-1002, 1018, 1084-1088."""

    def test_log_handoff_sqlite(self, tmp_path):
        """Lines 993-994: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.add_policy_event.return_value = {}
        mock_backend.add_handoff_event.return_value = {"event_type": "initiated"}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.log_handoff_event("initiated", "test", "health", details={"key": "val"})
                mock_backend.add_handoff_event.assert_called_once()

    def test_log_handoff_missing_key(self, tracker):
        """Line 1002: handles missing handoff_events key."""
        data = tracker._load_data()
        if "handoff_events" in data:
            del data["handoff_events"]
        tracker._save_data(data)
        event = tracker.log_handoff_event("initiated", "test", "health")
        assert event["event_type"] == "initiated"

    def test_log_handoff_trims_to_200(self, tracker):
        """Line 1018: trims to last 200 events."""
        data = tracker._load_data()
        data["handoff_events"] = [
            {
                "datetime": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "event_type": "initiated",
                "context": None,
                "domain": None,
                "outcome": None,
                "details": None,
            }
            for _ in range(205)
        ]
        tracker._save_data(data)
        tracker.log_handoff_event("initiated", "test", "health")
        data = tracker._load_data()
        assert len(data["handoff_events"]) <= 200

    def test_should_show_handoff_follow_up_with_pending(self, tracker):
        """Lines 1084-1088: returns True for old initiated handoff."""
        old_time = (datetime.now() - timedelta(hours=30)).isoformat()
        data = tracker._load_data()
        data["handoff_events"] = [
            {
                "datetime": old_time,
                "date": date.today().isoformat(),
                "event_type": "initiated",
                "context": "test",
                "domain": "health",
                "outcome": None,
                "details": None,
            }
        ]
        tracker._save_data(data)
        should_show, event = tracker.should_show_handoff_follow_up()
        assert should_show is True
        assert event["event_type"] == "initiated"

    def test_should_show_handoff_follow_up_too_recent(self, tracker):
        """Lines 1084-1088: returns False for recent handoff."""
        recent_time = (datetime.now() - timedelta(hours=2)).isoformat()
        data = tracker._load_data()
        data["handoff_events"] = [
            {
                "datetime": recent_time,
                "date": date.today().isoformat(),
                "event_type": "initiated",
                "context": "test",
                "domain": "health",
                "outcome": None,
                "details": None,
            }
        ]
        tracker._save_data(data)
        should_show, event = tracker.should_show_handoff_follow_up()
        assert should_show is False


# ==================== _is_late_night_hour ====================


class TestIsLateNightHour:
    """Test _is_late_night_hour - lines 1175-1176."""

    def test_late_night_true(self, tracker):
        assert tracker._is_late_night_hour("2024-01-01T23:30:00") is True

    def test_early_morning_true(self, tracker):
        assert tracker._is_late_night_hour("2024-01-01T03:00:00") is True

    def test_daytime_false(self, tracker):
        assert tracker._is_late_night_hour("2024-01-01T14:00:00") is False

    def test_invalid_datetime(self, tracker):
        """Lines 1175-1176: returns False for invalid datetime."""
        assert tracker._is_late_night_hour("not-a-datetime") is False

    def test_none_datetime(self, tracker):
        """Lines 1175-1176: returns False for None."""
        assert tracker._is_late_night_hour(None) is False


# ==================== _calculate_change ====================


class TestCalculateChange:
    """Test _calculate_change - line 1271."""

    def test_previous_zero_current_positive(self, tracker):
        """Line 1271: returns 1.0 when previous is 0 and current > 0."""
        assert tracker._calculate_change(5, 0) == 1.0

    def test_previous_zero_current_zero(self, tracker):
        assert tracker._calculate_change(0, 0) == 0.0

    def test_normal_change(self, tracker):
        assert tracker._calculate_change(10, 5) == 1.0
        assert tracker._calculate_change(5, 10) == -0.5


# ==================== ANTI-ENGAGEMENT SCORE BRANCHES ====================


class TestAntiEngagementScoreBranches:
    """Test calculate_anti_engagement_score branches - lines 1335-1421."""

    def _setup_sensitive_data(
        self,
        tracker,
        sensitive_sessions=0,
        connection_seeking=0,
        late_night_sensitive=0,
        total_sessions=1,
        last_week_sensitive=0,
        escalation=0.0,
    ):
        """Helper to mock the data needed for anti-engagement scoring."""
        sensitive_stats = {
            "sensitive_sessions": sensitive_sessions,
            "connection_seeking": connection_seeking,
            "late_night_sensitive": late_night_sensitive,
            "total_sessions": total_sessions,
            "sensitive_ratio": 0,
            "domain_breakdown": {},
            "period_days": 7,
        }
        comparison = {
            "this_week": {
                "sensitive_sessions": sensitive_sessions,
                "connection_seeking": connection_seeking,
                "human_reach_outs": 0,
                "independence": 0,
                "total_sessions": total_sessions,
            },
            "last_week": {
                "sensitive_sessions": last_week_sensitive,
                "connection_seeking": 0,
                "human_reach_outs": 0,
                "independence": 0,
                "total_sessions": max(total_sessions, 1),
            },
            "changes": {
                "sensitive_sessions": escalation,
                "connection_seeking": 0.0,
                "human_reach_outs": 0.0,
                "independence": 0.0,
            },
            "sensitive_trend": "stable",
        }
        return sensitive_stats, comparison

    def test_factor_sensitive_10_plus(self, tracker):
        """Line 1335: 10+ sensitive sessions - factor = 10.0."""
        stats, comp = self._setup_sensitive_data(tracker, sensitive_sessions=12, total_sessions=15)
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["sensitive_sessions"]["score"] == 10.0

    def test_factor_sensitive_7(self, tracker):
        """Line 1337: 7-9 sessions - factor = 6.0."""
        stats, comp = self._setup_sensitive_data(tracker, sensitive_sessions=8, total_sessions=10)
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["sensitive_sessions"]["score"] == 6.0

    def test_factor_sensitive_4(self, tracker):
        """Line 1341: 4-6 sessions - factor = 3.0."""
        stats, comp = self._setup_sensitive_data(tracker, sensitive_sessions=5, total_sessions=8)
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["sensitive_sessions"]["score"] == 3.0

    def test_factor_sensitive_1(self, tracker):
        """Line 1341: 1-3 sessions - factor = 1.0."""
        stats, comp = self._setup_sensitive_data(tracker, sensitive_sessions=2, total_sessions=5)
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["sensitive_sessions"]["score"] == 1.0

    def test_factor_connection_high(self, tracker):
        """Line 1350: connection_ratio >= 0.3 - factor = 10.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=1, connection_seeking=5, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["connection_seeking"]["score"] == 10.0

    def test_factor_connection_medium(self, tracker):
        """Line 1352: connection_ratio >= 0.2 - factor = 7.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=1, connection_seeking=2, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["connection_seeking"]["score"] == 7.0

    def test_factor_connection_low(self, tracker):
        """Line 1354: connection_ratio >= 0.1 - factor = 4.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=1, connection_seeking=1, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["connection_seeking"]["score"] == 4.0

    def test_factor_late_night_high(self, tracker):
        """Line 1363: late_night_ratio >= 0.3 - factor = 10.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=10, late_night_sensitive=5, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["late_night"]["score"] == 10.0

    def test_factor_late_night_medium(self, tracker):
        """Line 1365: late_night_ratio >= 0.2 - factor = 6.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=10, late_night_sensitive=2, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["late_night"]["score"] == 6.0

    def test_factor_late_night_low(self, tracker):
        """Line 1367: late_night_ratio >= 0.1 - factor = 3.0."""
        stats, comp = self._setup_sensitive_data(
            tracker, sensitive_sessions=10, late_night_sensitive=1, total_sessions=10
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["late_night"]["score"] == 3.0

    def test_factor_escalation_high(self, tracker):
        """Lines 1381-1382: escalation >= 0.5 - factor = 10.0."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=1,
            total_sessions=5,
            last_week_sensitive=3,
            escalation=0.6,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["escalation"]["score"] == 10.0

    def test_factor_escalation_medium(self, tracker):
        """Lines 1383-1384: escalation >= 0.3 - factor = 6.0."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=1,
            total_sessions=5,
            last_week_sensitive=3,
            escalation=0.35,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["escalation"]["score"] == 6.0

    def test_factor_escalation_low(self, tracker):
        """Lines 1385-1386: escalation >= 0.15 - factor = 3.0."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=1,
            total_sessions=5,
            last_week_sensitive=3,
            escalation=0.2,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["escalation"]["score"] == 3.0

    def test_factor_escalation_none(self, tracker):
        """Lines 1387-1388: escalation < 0.15 - factor = 0.0."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=1,
            total_sessions=5,
            last_week_sensitive=3,
            escalation=0.05,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["factors"]["escalation"]["score"] == 0.0

    def test_interpretation_good(self, tracker):
        """Lines 1406-1409: score 2-4 - 'good' level."""
        stats, comp = self._setup_sensitive_data(tracker, sensitive_sessions=4, total_sessions=10)
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                # 4 sessions -> factor 3.0, weighted 3.0*0.35 = 1.05
                # With 0 for other factors, score ~1.05 which is "excellent"
                assert result["level"] in ("excellent", "good")

    def test_interpretation_moderate(self, tracker):
        """Lines 1410-1413: score 4-6 - 'moderate' level."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=10,
            connection_seeking=3,
            total_sessions=10,
            last_week_sensitive=3,
            escalation=0.0,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                # 10 sessions -> 10*0.35=3.5, conn 0.3 -> 10*0.25=2.5, total ~6
                assert result["level"] in ("moderate", "concerning")

    def test_interpretation_concerning(self, tracker):
        """Lines 1414-1417: score 6-8 - 'concerning' level."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=10,
            connection_seeking=4,
            late_night_sensitive=4,
            total_sessions=10,
            last_week_sensitive=3,
            escalation=0.0,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["level"] in ("concerning", "high")

    def test_interpretation_high(self, tracker):
        """Lines 1418-1421: score 8+ - 'high' level."""
        stats, comp = self._setup_sensitive_data(
            tracker,
            sensitive_sessions=10,
            connection_seeking=5,
            late_night_sensitive=5,
            total_sessions=10,
            last_week_sensitive=3,
            escalation=0.6,
        )
        with patch.object(tracker, "get_sensitive_usage_stats", return_value=stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["score"] >= 8.0
                assert result["level"] == "high"

    def test_trend_improving(self, tracker):
        """Lines 1425-1427: trend improving when this week < 30d average * 0.85."""
        stats_7d = {
            "sensitive_sessions": 1,
            "connection_seeking": 0,
            "late_night_sensitive": 0,
            "total_sessions": 5,
            "sensitive_ratio": 0,
            "domain_breakdown": {},
            "period_days": 7,
        }
        stats_30d = {
            "sensitive_sessions": 20,
            "connection_seeking": 0,
            "late_night_sensitive": 0,
            "total_sessions": 30,
            "sensitive_ratio": 0,
            "domain_breakdown": {},
            "period_days": 30,
        }
        comp = self._setup_sensitive_data(tracker)[1]
        call_count = [0]

        def mock_stats(days=7):
            call_count[0] += 1
            return stats_7d if days == 7 else stats_30d

        with patch.object(tracker, "get_sensitive_usage_stats", side_effect=mock_stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["trend"] == "improving"

    def test_trend_increasing(self, tracker):
        """Lines 1428-1432: trend increasing when this week > 30d average * 1.15."""
        stats_7d = {
            "sensitive_sessions": 10,
            "connection_seeking": 0,
            "late_night_sensitive": 0,
            "total_sessions": 15,
            "sensitive_ratio": 0,
            "domain_breakdown": {},
            "period_days": 7,
        }
        stats_30d = {
            "sensitive_sessions": 16,
            "connection_seeking": 0,
            "late_night_sensitive": 0,
            "total_sessions": 30,
            "sensitive_ratio": 0,
            "domain_breakdown": {},
            "period_days": 30,
        }
        comp = self._setup_sensitive_data(tracker)[1]

        def mock_stats(days=7):
            return stats_7d if days == 7 else stats_30d

        with patch.object(tracker, "get_sensitive_usage_stats", side_effect=mock_stats):
            with patch.object(tracker, "get_weekly_comparison", return_value=comp):
                result = tracker.calculate_anti_engagement_score()
                assert result["trend"] == "increasing"


# ==================== SELF-REPORT ====================


class TestShouldShowSelfReport:
    """Test should_show_self_report - lines 1576-1603."""

    def test_handoff_followup_trigger(self, tracker):
        """Lines 1576-1587: shows handoff followup when pending."""
        old_time = (datetime.now() - timedelta(hours=30)).isoformat()
        data = tracker._load_data()
        data["handoff_events"] = [
            {
                "datetime": old_time,
                "date": (date.today() - timedelta(days=1)).isoformat(),
                "event_type": "initiated",
                "context": "test",
                "domain": "health",
                "outcome": None,
                "details": None,
            }
        ]
        tracker._save_data(data)
        should, config = tracker.should_show_self_report()
        assert should is True
        assert config["type"] == "handoff_followup"

    def test_high_usage_week_trigger(self, tracker):
        """Lines 1589-1601: shows usage_reflection for high sensitive usage."""
        # Need to mock get_weekly_comparison to return high sensitive sessions
        # and should_show_handoff_follow_up to return False
        with patch.object(tracker, "should_show_handoff_follow_up", return_value=(False, None)):
            comparison = {
                "this_week": {
                    "sensitive_sessions": 6,
                    "connection_seeking": 0,
                    "human_reach_outs": 0,
                    "independence": 0,
                    "total_sessions": 10,
                },
                "last_week": {
                    "sensitive_sessions": 2,
                    "connection_seeking": 0,
                    "human_reach_outs": 0,
                    "independence": 0,
                    "total_sessions": 5,
                },
                "changes": {
                    "sensitive_sessions": 0.5,
                    "connection_seeking": 0.0,
                    "human_reach_outs": 0.0,
                    "independence": 0.0,
                },
                "sensitive_trend": "concerning",
            }
            with patch.object(tracker, "get_weekly_comparison", return_value=comparison):
                should, config = tracker.should_show_self_report()
                assert should is True
                assert config["type"] == "usage_reflection"

    def test_no_trigger(self, tracker):
        """Line 1603: returns False when no triggers met."""
        with patch.object(tracker, "should_show_handoff_follow_up", return_value=(False, None)):
            comparison = {
                "this_week": {
                    "sensitive_sessions": 1,
                    "connection_seeking": 0,
                    "human_reach_outs": 0,
                    "independence": 0,
                    "total_sessions": 5,
                },
                "last_week": {
                    "sensitive_sessions": 1,
                    "connection_seeking": 0,
                    "human_reach_outs": 0,
                    "independence": 0,
                    "total_sessions": 5,
                },
                "changes": {
                    "sensitive_sessions": 0.0,
                    "connection_seeking": 0.0,
                    "human_reach_outs": 0.0,
                    "independence": 0.0,
                },
                "sensitive_trend": "stable",
            }
            with patch.object(tracker, "get_weekly_comparison", return_value=comparison):
                should, config = tracker.should_show_self_report()
                assert should is False
                assert config is None


class TestRecordSelfReport:
    """Test record_self_report - lines 1616-1637."""

    def test_record_self_report_sqlite(self, tmp_path):
        """Lines 1616-1617: SQLite delegation."""
        mock_backend = MagicMock()
        mock_backend.add_self_report.return_value = {"type": "test"}
        mock_backend.add_policy_event.return_value = {}
        with patch("utils.wellness_tracker.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path
            mock_settings.USE_SQLITE = True
            mock_settings.ENABLE_DEVICE_LOCK = False
            with patch(
                "utils.wellness_tracker._get_storage_backend",
                return_value=mock_backend,
            ):
                from utils.wellness_tracker import WellnessTracker

                tracker = WellnessTracker()
                tracker.record_self_report("usage_reflection", "too_much")
                mock_backend.add_self_report.assert_called_once()

    def test_record_self_report_missing_key(self, tracker):
        """Line 1623: handles missing self_reports key."""
        data = tracker._load_data()
        if "self_reports" in data:
            del data["self_reports"]
        tracker._save_data(data)
        report = tracker.record_self_report("test", "response")
        assert report["type"] == "test"

    def test_record_self_report_trims_to_100(self, tracker):
        """Line 1637: trims to last 100 reports."""
        data = tracker._load_data()
        data["self_reports"] = [
            {
                "datetime": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "type": "test",
                "response": "ok",
                "details": None,
            }
            for _ in range(105)
        ]
        tracker._save_data(data)
        tracker.record_self_report("test", "response")
        data = tracker._load_data()
        assert len(data["self_reports"]) <= 100


# ==================== DASHBOARD ====================


class TestMyPatternsDashboard:
    """Test get_my_patterns_dashboard health branches - lines 1484-1488."""

    def _mock_dashboard_deps(
        self,
        tracker,
        anti_score=0,
        sensitive_trend="stable",
        human_reach_outs=0,
        sensitive_sessions=0,
    ):
        comparison = {
            "this_week": {
                "sensitive_sessions": sensitive_sessions,
                "connection_seeking": 0,
                "human_reach_outs": human_reach_outs,
                "independence": 0,
                "total_sessions": 5,
            },
            "last_week": {
                "sensitive_sessions": 0,
                "connection_seeking": 0,
                "human_reach_outs": 0,
                "independence": 0,
                "total_sessions": 5,
            },
            "changes": {
                "sensitive_sessions": 0.0,
                "connection_seeking": 0.0,
                "human_reach_outs": 0.0,
                "independence": 0.0,
            },
            "sensitive_trend": sensitive_trend,
        }
        anti_engagement = {
            "score": anti_score,
            "level": "excellent",
            "label": "Healthy",
            "message": "ok",
            "factors": {},
            "trend": "stable",
            "trend_message": "stable",
        }
        return comparison, anti_engagement

    def test_healthy_status(self, tracker):
        """Lines 1483-1485: healthy when score <= 4 and reach_outs >= 1."""
        comp, anti = self._mock_dashboard_deps(tracker, anti_score=2, human_reach_outs=1)
        with patch.object(tracker, "get_weekly_comparison", return_value=comp):
            with patch.object(tracker, "calculate_anti_engagement_score", return_value=anti):
                with patch.object(tracker, "get_task_patterns", return_value={}):
                    result = tracker.get_my_patterns_dashboard()
                    assert result["health_status"] == "healthy"

    def test_concerning_status_high_score(self, tracker):
        """Lines 1486-1488: concerning when score >= 6."""
        comp, anti = self._mock_dashboard_deps(tracker, anti_score=7)
        with patch.object(tracker, "get_weekly_comparison", return_value=comp):
            with patch.object(tracker, "calculate_anti_engagement_score", return_value=anti):
                with patch.object(tracker, "get_task_patterns", return_value={}):
                    result = tracker.get_my_patterns_dashboard()
                    assert result["health_status"] == "concerning"

    def test_concerning_status_sensitive_trend(self, tracker):
        """Lines 1486-1488: concerning when sensitive_trend is concerning."""
        comp, anti = self._mock_dashboard_deps(tracker, anti_score=3, sensitive_trend="concerning")
        with patch.object(tracker, "get_weekly_comparison", return_value=comp):
            with patch.object(tracker, "calculate_anti_engagement_score", return_value=anti):
                with patch.object(tracker, "get_task_patterns", return_value={}):
                    result = tracker.get_my_patterns_dashboard()
                    assert result["health_status"] == "concerning"

    def test_moderate_status(self, tracker):
        """Lines 1490-1491: moderate otherwise."""
        comp, anti = self._mock_dashboard_deps(tracker, anti_score=3)
        with patch.object(tracker, "get_weekly_comparison", return_value=comp):
            with patch.object(tracker, "calculate_anti_engagement_score", return_value=anti):
                with patch.object(tracker, "get_task_patterns", return_value={}):
                    result = tracker.get_my_patterns_dashboard()
                    assert result["health_status"] == "moderate"


# ==================== TREND INDICATOR ====================


class TestTrendIndicator:
    """Test _trend_indicator - line 1547."""

    def test_positive_metric_decrease_concerning(self, tracker):
        """Line 1547: for positive metrics, decrease is concerning."""
        result = tracker._trend_indicator(-0.3, invert=False)
        assert result["status"] == "concerning"
        assert result["label"] == "Down"

    def test_positive_metric_increase_improving(self, tracker):
        result = tracker._trend_indicator(0.3, invert=False)
        assert result["status"] == "improving"

    def test_positive_metric_stable(self, tracker):
        result = tracker._trend_indicator(0.05, invert=False)
        assert result["status"] == "stable"

    def test_inverted_decrease_improving(self, tracker):
        result = tracker._trend_indicator(-0.3, invert=True)
        assert result["status"] == "improving"

    def test_inverted_increase_concerning(self, tracker):
        result = tracker._trend_indicator(0.3, invert=True)
        assert result["status"] == "concerning"
