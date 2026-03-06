"""
Storage Backend Abstraction for empathySync

Provides a unified interface for data storage that supports both:
- JSON files (current implementation, backward compatible)
- SQLite database (new implementation, better for multi-device sync)

The backend is selected based on settings.USE_SQLITE. When switching from
JSON to SQLite, data is automatically migrated.

Usage:
    from utils.storage_backend import get_storage_backend

    backend = get_storage_backend()

    # For WellnessTracker operations
    backend.add_check_in(feeling_score=4, notes="Feeling good")
    check_ins = backend.get_recent_check_ins(days=7)

    # For TrustedNetwork operations
    backend.add_trusted_person(name="Mom", relationship="parent")
    people = backend.get_all_trusted_people()
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from config.settings import settings
from utils.write_gate import check_write_permission, WriteBlockedError

logger = logging.getLogger(__name__)

# Singleton instance
_backend_instance = None


def get_storage_backend() -> "StorageBackend":
    """Get the storage backend singleton."""
    global _backend_instance

    if _backend_instance is None:
        if settings.USE_SQLITE:
            _backend_instance = SQLiteBackend()
        else:
            _backend_instance = JSONBackend()

    return _backend_instance


def reset_storage_backend():
    """Reset the backend singleton (for testing)."""
    global _backend_instance
    _backend_instance = None


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    def _ensure_write_allowed(self):
        """
        Check write permission before any write operation.

        Raises WriteBlockedError if in read-only mode.
        Subclasses should call this at the start of write methods.
        """
        check_write_permission()

    # ==================== CHECK-INS ====================

    @abstractmethod
    def add_check_in(self, feeling_score: int, notes: str = "") -> Dict:
        """Add a wellness check-in."""
        pass

    @abstractmethod
    def get_recent_check_ins(self, days: int = 7) -> List[Dict]:
        """Get check-ins from last N days."""
        pass

    @abstractmethod
    def get_check_in_for_date(self, target_date: date) -> Optional[Dict]:
        """Get check-in for a specific date."""
        pass

    # ==================== SESSIONS ====================

    @abstractmethod
    def add_session(
        self,
        duration_minutes: int,
        turn_count: int = 0,
        domains_touched: List[str] = None,
        max_risk_weight: float = 0,
        intent: str = None,
    ) -> Dict:
        """Add a usage session."""
        pass

    @abstractmethod
    def get_sessions_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        """Get sessions within a date range."""
        pass

    # ==================== POLICY EVENTS ====================

    @abstractmethod
    def add_policy_event(
        self,
        event_type: str,
        domain: str,
        action_taken: str,
        risk_weight: float = 0,
        explanation: str = "",
    ) -> Dict:
        """Log a policy event."""
        pass

    @abstractmethod
    def get_recent_policy_events(self, limit: int = 10) -> List[Dict]:
        """Get recent policy events."""
        pass

    # ==================== SESSION INTENTS ====================

    @abstractmethod
    def add_session_intent(
        self,
        intent: str,
        was_check_in: bool = False,
        auto_detected: bool = False,
        user_input: str = "",
    ) -> Dict:
        """Record session intent."""
        pass

    @abstractmethod
    def get_session_intents_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        """Get session intents within a date range."""
        pass

    # ==================== TASK PATTERNS ====================

    @abstractmethod
    def record_task_pattern(self, pattern_type: str, metadata: Dict = None) -> Dict:
        """Record a task pattern occurrence."""
        pass

    @abstractmethod
    def get_task_pattern_stats(self, pattern_type: str) -> Optional[Dict]:
        """Get stats for a task pattern."""
        pass

    @abstractmethod
    def get_all_task_patterns(self) -> Dict[str, Dict]:
        """Get all task pattern stats."""
        pass

    @abstractmethod
    def update_task_pattern(self, pattern_type: str, updates: Dict) -> None:
        """Update task pattern metadata."""
        pass

    # ==================== INDEPENDENCE RECORDS ====================

    @abstractmethod
    def add_independence_record(
        self, task_category: str, milestone: str = "", notes: str = ""
    ) -> Dict:
        """Record an independence achievement."""
        pass

    @abstractmethod
    def get_independence_records_for_period(
        self, start_date: date, end_date: date = None
    ) -> List[Dict]:
        """Get independence records within a date range."""
        pass

    # ==================== HANDOFF EVENTS ====================

    @abstractmethod
    def add_handoff_event(
        self,
        handoff_type: str,
        domain: str = None,
        person_name: str = None,
        completed: bool = False,
        notes: str = "",
    ) -> Dict:
        """Log a handoff event."""
        pass

    @abstractmethod
    def get_handoff_events_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        """Get handoff events within a date range."""
        pass

    @abstractmethod
    def update_handoff_event(self, event_id: int, updates: Dict) -> Optional[Dict]:
        """Update a handoff event."""
        pass

    # ==================== SELF-REPORTS ====================

    @abstractmethod
    def add_self_report(self, report_type: str, content: str = "", score: int = None) -> Dict:
        """Add a self-report entry."""
        pass

    @abstractmethod
    def get_recent_self_reports(self, limit: int = 10) -> List[Dict]:
        """Get recent self-reports."""
        pass

    # ==================== TRUSTED PEOPLE ====================

    @abstractmethod
    def add_trusted_person(
        self,
        name: str,
        relationship: str = "",
        contact: str = "",
        notes: str = "",
        domains: List[str] = None,
    ) -> Dict:
        """Add a trusted person."""
        pass

    @abstractmethod
    def get_all_trusted_people(self) -> List[Dict]:
        """Get all trusted people."""
        pass

    @abstractmethod
    def update_trusted_person(self, person_id: int, updates: Dict) -> Optional[Dict]:
        """Update a trusted person."""
        pass

    @abstractmethod
    def remove_trusted_person(self, person_id: int) -> bool:
        """Remove a trusted person."""
        pass

    # ==================== REACH-OUTS ====================

    @abstractmethod
    def add_reach_out(
        self,
        person_id: int = None,
        person_name: str = "",
        method: str = "",
        notes: str = "",
        outcome: str = "",
    ) -> Dict:
        """Log a reach-out to a trusted person."""
        pass

    @abstractmethod
    def get_reach_outs_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        """Get reach-outs within a date range."""
        pass

    # ==================== DATA MANAGEMENT ====================

    @abstractmethod
    def prune_old_data(self, retention_days: int) -> int:
        """Delete records older than retention_days. Returns count of pruned records."""
        pass

    @abstractmethod
    def clear_all_data(self) -> None:
        """Clear all stored data."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        pass


class JSONBackend(StorageBackend):
    """
    JSON file-based storage backend.

    This is the original storage method, maintained for backward compatibility.
    Data is stored in two files: wellness_data.json and trusted_network.json.
    """

    def __init__(self):
        self.wellness_file = settings.DATA_DIR / "wellness_data.json"
        self.network_file = settings.DATA_DIR / "trusted_network.json"
        self._ensure_files()

    def _ensure_files(self):
        """Ensure data files exist."""
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

        if not self.wellness_file.exists():
            self._save_wellness(self._get_default_wellness())

        if not self.network_file.exists():
            self._save_network(self._get_default_network())

    def _get_default_wellness(self) -> Dict:
        return {
            "schema_version": 1,
            "check_ins": [],
            "usage_sessions": [],
            "policy_events": [],
            "session_intents": [],
            "independence_records": [],
            "handoff_events": [],
            "self_reports": [],
            "task_patterns": {},
            "created_at": datetime.now().isoformat(),
        }

    def _get_default_network(self) -> Dict:
        return {
            "schema_version": 1,
            "people": [],
            "reach_outs": [],
            "handoffs": [],
            "created_at": datetime.now().isoformat(),
        }

    def _load_wellness(self) -> Dict:
        try:
            with open(self.wellness_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self._get_default_wellness()

    def _save_wellness(self, data: Dict):
        import tempfile
        import os

        fd, temp_path = tempfile.mkstemp(
            dir=self.wellness_file.parent, prefix=".wellness_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.wellness_file)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _load_network(self) -> Dict:
        try:
            with open(self.network_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self._get_default_network()

    def _save_network(self, data: Dict):
        import tempfile
        import os

        fd, temp_path = tempfile.mkstemp(
            dir=self.network_file.parent, prefix=".network_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.network_file)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    # ==================== CHECK-INS ====================

    def add_check_in(self, feeling_score: int, notes: str = "") -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        check_in = {
            "id": len(data["check_ins"]) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "feeling_score": feeling_score,
            "notes": notes,
        }
        data["check_ins"].append(check_in)
        self._save_wellness(data)
        return check_in

    def get_recent_check_ins(self, days: int = 7) -> List[Dict]:
        data = self._load_wellness()
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return [c for c in data.get("check_ins", []) if c.get("date", "") >= cutoff]

    def get_check_in_for_date(self, target_date: date) -> Optional[Dict]:
        data = self._load_wellness()
        target_str = target_date.isoformat()
        for check_in in reversed(data.get("check_ins", [])):
            if check_in.get("date") == target_str:
                return check_in
        return None

    # ==================== SESSIONS ====================

    def add_session(
        self,
        duration_minutes: int,
        turn_count: int = 0,
        domains_touched: List[str] = None,
        max_risk_weight: float = 0,
        intent: str = None,
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        session = {
            "id": len(data["usage_sessions"]) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "hour": datetime.now().hour,
            "duration_minutes": duration_minutes,
            "turn_count": turn_count,
            "domains_touched": domains_touched or [],
            "max_risk_weight": max_risk_weight,
            "intent": intent,
        }
        data["usage_sessions"].append(session)
        self._save_wellness(data)
        return session

    def get_sessions_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        data = self._load_wellness()
        start_str = start_date.isoformat()
        end_str = (end_date or date.today()).isoformat()
        return [
            s for s in data.get("usage_sessions", []) if start_str <= s.get("date", "") <= end_str
        ]

    # ==================== POLICY EVENTS ====================

    def add_policy_event(
        self,
        event_type: str,
        domain: str,
        action_taken: str,
        risk_weight: float = 0,
        explanation: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        event = {
            "id": len(data.get("policy_events", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "event_type": event_type,
            "domain": domain,
            "action_taken": action_taken,
            "risk_weight": risk_weight,
            "explanation": explanation,
        }
        if "policy_events" not in data:
            data["policy_events"] = []
        data["policy_events"].append(event)
        self._save_wellness(data)
        return event

    def get_recent_policy_events(self, limit: int = 10) -> List[Dict]:
        data = self._load_wellness()
        events = data.get("policy_events", [])
        return events[-limit:] if events else []

    # ==================== SESSION INTENTS ====================

    def add_session_intent(
        self,
        intent: str,
        was_check_in: bool = False,
        auto_detected: bool = False,
        user_input: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        record = {
            "id": len(data.get("session_intents", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "intent": intent,
            "was_check_in": was_check_in,
            "auto_detected": auto_detected,
            "user_input": user_input,
        }
        if "session_intents" not in data:
            data["session_intents"] = []
        data["session_intents"].append(record)
        self._save_wellness(data)
        return record

    def get_session_intents_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        data = self._load_wellness()
        start_str = start_date.isoformat()
        end_str = (end_date or date.today()).isoformat()
        return [
            i for i in data.get("session_intents", []) if start_str <= i.get("date", "") <= end_str
        ]

    # ==================== TASK PATTERNS ====================

    def record_task_pattern(self, pattern_type: str, metadata: Dict = None) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        if "task_patterns" not in data:
            data["task_patterns"] = {}

        if pattern_type not in data["task_patterns"]:
            data["task_patterns"][pattern_type] = {
                "count": 0,
                "first_use": datetime.now().isoformat(),
                "uses": [],
                "graduation_shown_count": 0,
                "dismissal_count": 0,
                "metadata": metadata or {},
            }

        pattern = data["task_patterns"][pattern_type]
        pattern["count"] += 1
        pattern["last_use"] = datetime.now().isoformat()
        pattern["uses"].append(
            {"datetime": datetime.now().isoformat(), "date": date.today().isoformat()}
        )

        # Keep only last 100 uses
        if len(pattern["uses"]) > 100:
            pattern["uses"] = pattern["uses"][-100:]

        self._save_wellness(data)
        return self._calculate_pattern_stats(pattern_type, pattern)

    def _calculate_pattern_stats(self, pattern_type: str, pattern: Dict) -> Dict:
        uses = pattern.get("uses", [])
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        month_ago = (date.today() - timedelta(days=30)).isoformat()

        return {
            "pattern_type": pattern_type,
            "count": pattern.get("count", 0),
            "last_7_days": sum(1 for u in uses if u.get("date", "") >= week_ago),
            "last_30_days": sum(1 for u in uses if u.get("date", "") >= month_ago),
            "first_use": pattern.get("first_use"),
            "last_use": pattern.get("last_use"),
            "graduation_shown_count": pattern.get("graduation_shown_count", 0),
            "dismissal_count": pattern.get("dismissal_count", 0),
        }

    def get_task_pattern_stats(self, pattern_type: str) -> Optional[Dict]:
        data = self._load_wellness()
        patterns = data.get("task_patterns", {})
        if pattern_type in patterns:
            return self._calculate_pattern_stats(pattern_type, patterns[pattern_type])
        return None

    def get_all_task_patterns(self) -> Dict[str, Dict]:
        data = self._load_wellness()
        patterns = data.get("task_patterns", {})
        return {pt: self._calculate_pattern_stats(pt, p) for pt, p in patterns.items()}

    def update_task_pattern(self, pattern_type: str, updates: Dict) -> None:
        self._ensure_write_allowed()
        data = self._load_wellness()
        if "task_patterns" in data and pattern_type in data["task_patterns"]:
            data["task_patterns"][pattern_type].update(updates)
            self._save_wellness(data)

    # ==================== INDEPENDENCE RECORDS ====================

    def add_independence_record(
        self, task_category: str, milestone: str = "", notes: str = ""
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        record = {
            "id": len(data.get("independence_records", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "task_category": task_category,
            "milestone": milestone,
            "notes": notes,
        }
        if "independence_records" not in data:
            data["independence_records"] = []
        data["independence_records"].append(record)
        self._save_wellness(data)
        return record

    def get_independence_records_for_period(
        self, start_date: date, end_date: date = None
    ) -> List[Dict]:
        data = self._load_wellness()
        start_str = start_date.isoformat()
        end_str = (end_date or date.today()).isoformat()
        return [
            r
            for r in data.get("independence_records", [])
            if start_str <= r.get("date", "") <= end_str
        ]

    # ==================== HANDOFF EVENTS ====================

    def add_handoff_event(
        self,
        handoff_type: str,
        domain: str = None,
        person_name: str = None,
        completed: bool = False,
        notes: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        event = {
            "id": len(data.get("handoff_events", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "handoff_type": handoff_type,
            "domain": domain,
            "person_name": person_name,
            "completed": completed,
            "notes": notes,
        }
        if "handoff_events" not in data:
            data["handoff_events"] = []
        data["handoff_events"].append(event)
        self._save_wellness(data)
        return event

    def get_handoff_events_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        data = self._load_wellness()
        start_str = start_date.isoformat()
        end_str = (end_date or date.today()).isoformat()
        return [
            e for e in data.get("handoff_events", []) if start_str <= e.get("date", "") <= end_str
        ]

    def update_handoff_event(self, event_id: int, updates: Dict) -> Optional[Dict]:
        self._ensure_write_allowed()
        data = self._load_wellness()
        for event in data.get("handoff_events", []):
            if event.get("id") == event_id:
                event.update(updates)
                self._save_wellness(data)
                return event
        return None

    # ==================== SELF-REPORTS ====================

    def add_self_report(self, report_type: str, content: str = "", score: int = None) -> Dict:
        self._ensure_write_allowed()
        data = self._load_wellness()
        report = {
            "id": len(data.get("self_reports", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "report_type": report_type,
            "content": content,
            "score": score,
        }
        if "self_reports" not in data:
            data["self_reports"] = []
        data["self_reports"].append(report)
        self._save_wellness(data)
        return report

    def get_recent_self_reports(self, limit: int = 10) -> List[Dict]:
        data = self._load_wellness()
        reports = data.get("self_reports", [])
        return reports[-limit:] if reports else []

    # ==================== TRUSTED PEOPLE ====================

    def add_trusted_person(
        self,
        name: str,
        relationship: str = "",
        contact: str = "",
        notes: str = "",
        domains: List[str] = None,
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_network()
        person = {
            "id": len(data["people"]) + 1,
            "name": name,
            "relationship": relationship,
            "contact": contact,
            "notes": notes,
            "domains": domains or [],
            "added_at": datetime.now().isoformat(),
            "last_contact": None,
        }
        data["people"].append(person)
        self._save_network(data)
        return person

    def get_all_trusted_people(self) -> List[Dict]:
        data = self._load_network()
        return data.get("people", [])

    def update_trusted_person(self, person_id: int, updates: Dict) -> Optional[Dict]:
        self._ensure_write_allowed()
        data = self._load_network()
        for person in data["people"]:
            if person["id"] == person_id:
                person.update(updates)
                self._save_network(data)
                return person
        return None

    def remove_trusted_person(self, person_id: int) -> bool:
        self._ensure_write_allowed()
        data = self._load_network()
        original_count = len(data["people"])
        data["people"] = [p for p in data["people"] if p["id"] != person_id]
        if len(data["people"]) < original_count:
            self._save_network(data)
            return True
        return False

    # ==================== REACH-OUTS ====================

    def add_reach_out(
        self,
        person_id: int = None,
        person_name: str = "",
        method: str = "",
        notes: str = "",
        outcome: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        data = self._load_network()
        reach_out = {
            "id": len(data.get("reach_outs", [])) + 1,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "person_id": person_id,
            "person_name": person_name,
            "method": method,
            "notes": notes,
            "outcome": outcome,
        }
        if "reach_outs" not in data:
            data["reach_outs"] = []
        data["reach_outs"].append(reach_out)

        # Update last_contact for the person
        if person_id:
            for person in data["people"]:
                if person["id"] == person_id:
                    person["last_contact"] = date.today().isoformat()
                    break
        elif person_name:
            for person in data["people"]:
                if person["name"].lower() == person_name.lower():
                    person["last_contact"] = date.today().isoformat()
                    break

        self._save_network(data)
        return reach_out

    def get_reach_outs_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        data = self._load_network()
        start_str = start_date.isoformat()
        end_str = (end_date or date.today()).isoformat()
        return [r for r in data.get("reach_outs", []) if start_str <= r.get("date", "") <= end_str]

    # ==================== DATA MANAGEMENT ====================

    def prune_old_data(self, retention_days: int) -> int:
        self._ensure_write_allowed()
        cutoff = (date.today() - timedelta(days=retention_days)).isoformat()
        pruned = 0

        data = self._load_wellness()
        date_lists = [
            "check_ins",
            "usage_sessions",
            "policy_events",
            "session_intents",
            "independence_records",
            "handoff_events",
            "self_reports",
        ]
        for key in date_lists:
            original = data.get(key, [])
            filtered = [r for r in original if r.get("date", "") >= cutoff]
            pruned += len(original) - len(filtered)
            data[key] = filtered

        if pruned > 0:
            self._save_wellness(data)
            logger.info(f"Pruned {pruned} records older than {retention_days} days")

        return pruned

    def clear_all_data(self) -> None:
        self._ensure_write_allowed()
        self._save_wellness(self._get_default_wellness())
        self._save_network(self._get_default_network())

    def close(self) -> None:
        # No connections to close for JSON backend
        pass


class SQLiteBackend(StorageBackend):
    """
    SQLite database storage backend.

    Uses the database module for all operations. Provides better performance
    for concurrent access and partial updates.
    """

    # Column whitelists per table — prevents SQL injection via dynamic column names
    _VALID_COLUMNS = {
        "task_patterns": frozenset(
            {
                "pattern_type",
                "count",
                "last_7_days",
                "last_used",
                "metadata",
            }
        ),
        "handoff_events": frozenset(
            {
                "context",
                "domain",
                "person_name",
                "message_preview",
                "status",
                "outcome",
                "reached_out",
                "outcome_date",
                "follow_up_shown",
                "follow_up_shown_date",
                "completed",
            }
        ),
        "trusted_people": frozenset(
            {
                "name",
                "relationship",
                "contact",
                "notes",
                "domains",
                "last_contact",
            }
        ),
    }

    def _validate_columns(self, table: str, columns: dict) -> dict:
        """
        Validate column names against whitelist. Raises ValueError on unknown columns.
        Returns the filtered dict (only valid columns).
        """
        valid = self._VALID_COLUMNS.get(table)
        if valid is None:
            raise ValueError(f"No column whitelist defined for table: {table}")
        invalid = set(columns.keys()) - valid
        if invalid:
            raise ValueError(
                f"Invalid column(s) for {table}: {invalid}. " f"Valid columns: {valid}"
            )
        return columns

    def __init__(self):
        # Import here to avoid circular imports
        from utils.database import get_db, close_db, migrate_from_json

        self._get_db = get_db
        self._close_db = close_db
        self._migrate_from_json = migrate_from_json

        # Check if migration from JSON is needed
        self._maybe_migrate_from_json()

    def _maybe_migrate_from_json(self):
        """Migrate from JSON if old files exist and DB hasn't been migrated yet."""
        wellness_json = settings.DATA_DIR / "wellness_data.json"
        network_json = settings.DATA_DIR / "trusted_network.json"

        # Check if JSON files exist
        if not wellness_json.exists() and not network_json.exists():
            return

        db = self._get_db()

        # Check if migration was already performed by looking for migration marker
        # This is more reliable than checking data counts
        try:
            result = db.execute(
                "SELECT 1 FROM schema_info WHERE description LIKE '%migrated from JSON%' LIMIT 1"
            ).fetchone()
            if result:
                logger.info("JSON migration already performed, skipping")
                return
        except Exception:
            pass  # Table might not exist yet

        # Fallback: check if any core table has data
        for table in ["check_ins", "usage_sessions", "policy_events", "trusted_people"]:
            try:
                count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                if count and count[0] > 0:
                    logger.info(f"SQLite already has data in {table}, skipping JSON migration")
                    return
            except Exception:
                pass  # Table might not exist

        # Perform migration
        logger.info("Migrating data from JSON to SQLite...")
        success = self._migrate_from_json(wellness_json, network_json)

        if success:
            # Record migration marker to prevent re-running
            try:
                db.execute(
                    "INSERT INTO schema_info (version, migrated_at, description) VALUES (?, datetime('now'), ?)",
                    (0, "Data migrated from JSON files"),
                )
                db.commit()
            except Exception as e:
                logger.warning(f"Could not record migration marker: {e}")

            # Archive JSON files
            archive_dir = settings.DATA_DIR / "archive"
            archive_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if wellness_json.exists():
                wellness_json.rename(archive_dir / f"wellness_data.{timestamp}.json")
            if network_json.exists():
                network_json.rename(archive_dir / f"trusted_network.{timestamp}.json")

            logger.info("JSON files archived after successful migration")

    @property
    def db(self):
        return self._get_db()

    # ==================== CHECK-INS ====================

    def add_check_in(self, feeling_score: int, notes: str = "") -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            "INSERT INTO check_ins (feeling_score, notes) VALUES (?, ?)", (feeling_score, notes)
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "feeling_score": feeling_score,
            "notes": notes,
        }

    def get_recent_check_ins(self, days: int = 7) -> List[Dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = self.db.execute(
            "SELECT * FROM check_ins WHERE created_at >= ? ORDER BY created_at DESC", (cutoff,)
        ).fetchall()

        return [dict(row) for row in rows]

    def get_check_in_for_date(self, target_date: date) -> Optional[Dict]:
        start = datetime.combine(target_date, datetime.min.time()).isoformat()
        end = datetime.combine(target_date, datetime.max.time()).isoformat()

        row = self.db.execute(
            "SELECT * FROM check_ins WHERE created_at BETWEEN ? AND ? LIMIT 1", (start, end)
        ).fetchone()

        return dict(row) if row else None

    # ==================== SESSIONS ====================

    def add_session(
        self,
        duration_minutes: int,
        turn_count: int = 0,
        domains_touched: List[str] = None,
        max_risk_weight: float = 0,
        intent: str = None,
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            """INSERT INTO usage_sessions
               (duration_minutes, turn_count, domains_touched, max_risk_weight, intent)
               VALUES (?, ?, ?, ?, ?)""",
            (
                duration_minutes,
                turn_count,
                json.dumps(domains_touched or []),
                max_risk_weight,
                intent,
            ),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "hour": datetime.now().hour,
            "duration_minutes": duration_minutes,
            "turn_count": turn_count,
            "domains_touched": domains_touched or [],
            "max_risk_weight": max_risk_weight,
            "intent": intent,
        }

    def get_sessions_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(end_date or date.today(), datetime.max.time()).isoformat()

        rows = self.db.execute(
            "SELECT * FROM usage_sessions WHERE started_at BETWEEN ? AND ?", (start, end)
        ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            if d.get("domains_touched"):
                d["domains_touched"] = json.loads(d["domains_touched"])
            result.append(d)
        return result

    # ==================== POLICY EVENTS ====================

    def add_policy_event(
        self,
        event_type: str,
        domain: str,
        action_taken: str,
        risk_weight: float = 0,
        explanation: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            """INSERT INTO policy_events
               (event_type, domain, action_taken, risk_weight, explanation)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, domain, action_taken, risk_weight, explanation),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "event_type": event_type,
            "domain": domain,
            "action_taken": action_taken,
            "risk_weight": risk_weight,
            "explanation": explanation,
        }

    def get_recent_policy_events(self, limit: int = 10) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM policy_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================== SESSION INTENTS ====================

    def add_session_intent(
        self,
        intent: str,
        was_check_in: bool = False,
        auto_detected: bool = False,
        user_input: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            "INSERT INTO session_intents (intent, user_input) VALUES (?, ?)", (intent, user_input)
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "intent": intent,
            "was_check_in": was_check_in,
            "auto_detected": auto_detected,
            "user_input": user_input,
        }

    def get_session_intents_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(end_date or date.today(), datetime.max.time()).isoformat()

        rows = self.db.execute(
            "SELECT * FROM session_intents WHERE created_at BETWEEN ? AND ?", (start, end)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================== TASK PATTERNS ====================

    def record_task_pattern(self, pattern_type: str, metadata: Dict = None) -> Dict:
        self._ensure_write_allowed()
        # Check if pattern exists
        row = self.db.execute(
            "SELECT * FROM task_patterns WHERE pattern_type = ?", (pattern_type,)
        ).fetchone()

        if row:
            # Update existing
            self.db.execute(
                """UPDATE task_patterns
                   SET count = count + 1, last_seen = datetime('now')
                   WHERE pattern_type = ?""",
                (pattern_type,),
            )
        else:
            # Insert new
            self.db.execute(
                """INSERT INTO task_patterns (pattern_type, metadata)
                   VALUES (?, ?)""",
                (pattern_type, json.dumps(metadata or {})),
            )

        self.db.commit()
        return self.get_task_pattern_stats(pattern_type)

    def get_task_pattern_stats(self, pattern_type: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM task_patterns WHERE pattern_type = ?", (pattern_type,)
        ).fetchone()

        if not row:
            return None

        d = dict(row)
        if d.get("metadata"):
            d["metadata"] = json.loads(d["metadata"])
        return d

    def get_all_task_patterns(self) -> Dict[str, Dict]:
        rows = self.db.execute("SELECT * FROM task_patterns").fetchall()
        result = {}
        for row in rows:
            d = dict(row)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            result[d["pattern_type"]] = d
        return result

    def update_task_pattern(self, pattern_type: str, updates: Dict) -> None:
        self._ensure_write_allowed()
        self._validate_columns("task_patterns", updates)
        # Build update query dynamically
        set_parts = []
        values = []
        for key, value in updates.items():
            if key == "metadata":
                value = json.dumps(value)
            set_parts.append(f"{key} = ?")
            values.append(value)

        if set_parts:
            values.append(pattern_type)
            self.db.execute(
                f"UPDATE task_patterns SET {', '.join(set_parts)} WHERE pattern_type = ?",
                tuple(values),
            )
            self.db.commit()

    # ==================== INDEPENDENCE RECORDS ====================

    def add_independence_record(
        self, task_category: str, milestone: str = "", notes: str = ""
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            "INSERT INTO independence_records (task_category, milestone, notes) VALUES (?, ?, ?)",
            (task_category, milestone, notes),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "task_category": task_category,
            "milestone": milestone,
            "notes": notes,
        }

    def get_independence_records_for_period(
        self, start_date: date, end_date: date = None
    ) -> List[Dict]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(end_date or date.today(), datetime.max.time()).isoformat()

        rows = self.db.execute(
            "SELECT * FROM independence_records WHERE created_at BETWEEN ? AND ?", (start, end)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================== HANDOFF EVENTS ====================

    def add_handoff_event(
        self,
        handoff_type: str,
        domain: str = None,
        person_name: str = None,
        completed: bool = False,
        notes: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            """INSERT INTO handoff_events
               (handoff_type, domain, person_name, completed, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (handoff_type, domain, person_name, 1 if completed else 0, notes),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "handoff_type": handoff_type,
            "domain": domain,
            "person_name": person_name,
            "completed": completed,
            "notes": notes,
        }

    def get_handoff_events_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(end_date or date.today(), datetime.max.time()).isoformat()

        rows = self.db.execute(
            "SELECT * FROM handoff_events WHERE created_at BETWEEN ? AND ?", (start, end)
        ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            d["completed"] = bool(d.get("completed"))
            result.append(d)
        return result

    def update_handoff_event(self, event_id: int, updates: Dict) -> Optional[Dict]:
        self._ensure_write_allowed()
        self._validate_columns("handoff_events", updates)
        # Build update query
        set_parts = []
        values = []
        for key, value in updates.items():
            if key == "completed":
                value = 1 if value else 0
            set_parts.append(f"{key} = ?")
            values.append(value)

        if set_parts:
            values.append(event_id)
            self.db.execute(
                f"UPDATE handoff_events SET {', '.join(set_parts)} WHERE id = ?", tuple(values)
            )
            self.db.commit()

        row = self.db.execute("SELECT * FROM handoff_events WHERE id = ?", (event_id,)).fetchone()

        if row:
            d = dict(row)
            d["completed"] = bool(d.get("completed"))
            return d
        return None

    # ==================== SELF-REPORTS ====================

    def add_self_report(self, report_type: str, content: str = "", score: int = None) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            "INSERT INTO self_reports (report_type, content, score) VALUES (?, ?, ?)",
            (report_type, content, score),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "report_type": report_type,
            "content": content,
            "score": score,
        }

    def get_recent_self_reports(self, limit: int = 10) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM self_reports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================== TRUSTED PEOPLE ====================

    def add_trusted_person(
        self,
        name: str,
        relationship: str = "",
        contact: str = "",
        notes: str = "",
        domains: List[str] = None,
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            """INSERT INTO trusted_people
               (name, relationship, contact, notes, domains)
               VALUES (?, ?, ?, ?, ?)""",
            (name, relationship, contact, notes, json.dumps(domains or [])),
        )
        self.db.commit()

        return {
            "id": cursor.lastrowid,
            "name": name,
            "relationship": relationship,
            "contact": contact,
            "notes": notes,
            "domains": domains or [],
            "added_at": datetime.now().isoformat(),
            "last_contact": None,
        }

    def get_all_trusted_people(self) -> List[Dict]:
        rows = self.db.execute("SELECT * FROM trusted_people").fetchall()

        result = []
        for row in rows:
            d = dict(row)
            if d.get("domains"):
                d["domains"] = json.loads(d["domains"])
            result.append(d)
        return result

    def update_trusted_person(self, person_id: int, updates: Dict) -> Optional[Dict]:
        self._ensure_write_allowed()
        self._validate_columns("trusted_people", updates)
        set_parts = []
        values = []
        for key, value in updates.items():
            if key == "domains":
                value = json.dumps(value)
            set_parts.append(f"{key} = ?")
            values.append(value)

        if set_parts:
            values.append(person_id)
            self.db.execute(
                f"UPDATE trusted_people SET {', '.join(set_parts)} WHERE id = ?", tuple(values)
            )
            self.db.commit()

        row = self.db.execute("SELECT * FROM trusted_people WHERE id = ?", (person_id,)).fetchone()

        if row:
            d = dict(row)
            if d.get("domains"):
                d["domains"] = json.loads(d["domains"])
            return d
        return None

    def remove_trusted_person(self, person_id: int) -> bool:
        self._ensure_write_allowed()
        cursor = self.db.execute("DELETE FROM trusted_people WHERE id = ?", (person_id,))
        self.db.commit()
        return cursor.rowcount > 0

    # ==================== REACH-OUTS ====================

    def add_reach_out(
        self,
        person_id: int = None,
        person_name: str = "",
        method: str = "",
        notes: str = "",
        outcome: str = "",
    ) -> Dict:
        self._ensure_write_allowed()
        cursor = self.db.execute(
            "INSERT INTO reach_outs (person_id, method, notes, outcome) VALUES (?, ?, ?, ?)",
            (person_id, method, notes, outcome),
        )
        self.db.commit()

        # Update last_contact for person
        if person_id:
            self.db.execute(
                "UPDATE trusted_people SET last_contact = datetime('now') WHERE id = ?",
                (person_id,),
            )
            self.db.commit()

        return {
            "id": cursor.lastrowid,
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "person_id": person_id,
            "person_name": person_name,
            "method": method,
            "notes": notes,
            "outcome": outcome,
        }

    def get_reach_outs_for_period(self, start_date: date, end_date: date = None) -> List[Dict]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(end_date or date.today(), datetime.max.time()).isoformat()

        rows = self.db.execute(
            "SELECT * FROM reach_outs WHERE created_at BETWEEN ? AND ?", (start, end)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==================== DATA MANAGEMENT ====================

    def prune_old_data(self, retention_days: int) -> int:
        self._ensure_write_allowed()
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        pruned = 0

        # Tables with created_at timestamp columns
        tables_with_created_at = [
            "check_ins",
            "usage_sessions",
            "policy_events",
            "session_intents",
            "independence_records",
            "handoff_events",
            "self_reports",
        ]
        for table in tables_with_created_at:
            cursor = self.db.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
            pruned += cursor.rowcount

        if pruned > 0:
            self.db.commit()
            logger.info(f"Pruned {pruned} records older than {retention_days} days")

        return pruned

    def clear_all_data(self) -> None:
        self._ensure_write_allowed()
        tables = [
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
        ]
        for table in tables:
            self.db.execute(f"DELETE FROM {table}")
        self.db.commit()

    def close(self) -> None:
        self._close_db()
