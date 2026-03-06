"""
Wellness tracking for empathySync users
Local storage of wellness check-ins, usage patterns, and dependency monitoring

Supports two storage backends:
- JSON files (default, backward compatible)
- SQLite database (when USE_SQLITE=true, better for multi-device sync)
"""

import json
import os
import tempfile
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)


def _get_storage_backend():
    """Lazy import to avoid circular dependency."""
    if settings.USE_SQLITE:
        from utils.storage_backend import get_storage_backend

        return get_storage_backend()
    return None


# Schema version for data migration support
SCHEMA_VERSION = 1


# Session intent types
INTENT_PRACTICAL = "practical"
INTENT_PROCESSING = "processing"
INTENT_CONNECTION = "connection"
INTENT_UNKNOWN = "unknown"


class WellnessTracker:
    """
    Track user wellness patterns locally.

    Monitors session frequency, duration, and patterns to detect
    dependency and enforce healthy usage boundaries.

    Supports two storage backends:
    - JSON files (default)
    - SQLite database (when settings.USE_SQLITE is True)
    """

    def __init__(self):
        self.data_file = settings.DATA_DIR / "wellness_data.json"
        self._backend = _get_storage_backend()
        self.ensure_data_file()

    def ensure_data_file(self):
        """Ensure wellness data file exists with current schema"""
        if not self.data_file.exists():
            self._save_data(self._get_default_data())

    def _get_default_data(self) -> Dict:
        """Return default data structure with current schema version"""
        return {
            "schema_version": SCHEMA_VERSION,
            "check_ins": [],
            "usage_sessions": [],
            "policy_events": [],
            "session_intents": [],
            "independence_records": [],
            "handoff_events": [],
            "self_reports": [],
            "created_at": datetime.now().isoformat(),
        }

    # ==================== CHECK-INS ====================

    def add_check_in(self, feeling_score: int, notes: str = ""):
        """Add a wellness check-in (1-5 scale)"""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_check_in(feeling_score, notes)

        # JSON backend
        data = self._load_data()

        check_in = {
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "feeling_score": feeling_score,
            "notes": notes,
        }

        data["check_ins"].append(check_in)
        self._save_data(data)

        return check_in

    def get_recent_check_ins(self, days: int = 7) -> List[Dict]:
        """Get check-ins from last N days"""
        data = self._load_data()
        recent = data["check_ins"][-days:] if data["check_ins"] else []
        return recent

    def get_today_check_in(self) -> Optional[Dict]:
        """Check if user has checked in today"""
        today_str = date.today().isoformat()
        data = self._load_data()

        for check_in in reversed(data["check_ins"]):
            if check_in["date"] == today_str:
                return check_in

        return None

    # ==================== SESSION TRACKING ====================

    def add_session(
        self,
        duration_minutes: int,
        turn_count: int = 0,
        domains_touched: List[str] = None,
        max_risk_weight: float = 0,
    ):
        """
        Track a usage session with rich metadata.

        Args:
            duration_minutes: How long the session lasted
            turn_count: Number of conversation turns
            domains_touched: List of risk domains encountered
            max_risk_weight: Highest risk weight seen in session
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_session(
                duration_minutes, turn_count, domains_touched, max_risk_weight
            )

        # JSON backend
        data = self._load_data()

        session = {
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "hour": datetime.now().hour,
            "duration_minutes": duration_minutes,
            "turn_count": turn_count,
            "domains_touched": domains_touched or [],
            "max_risk_weight": max_risk_weight,
        }

        data["usage_sessions"].append(session)
        self._save_data(data)

        return session

    def get_sessions_today(self) -> List[Dict]:
        """Get all sessions from today"""
        today_str = date.today().isoformat()
        data = self._load_data()

        return [s for s in data.get("usage_sessions", []) if s.get("date") == today_str]

    def get_sessions_this_week(self) -> List[Dict]:
        """Get all sessions from the past 7 days"""
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        data = self._load_data()

        return [s for s in data.get("usage_sessions", []) if s.get("date", "") >= week_ago]

    def count_sessions_today(self) -> int:
        """Count number of sessions today"""
        return len(self.get_sessions_today())

    def count_sessions_this_week(self) -> int:
        """Count number of sessions this week"""
        return len(self.get_sessions_this_week())

    def get_total_minutes_today(self) -> int:
        """Get total minutes spent in sessions today"""
        sessions = self.get_sessions_today()
        return sum(s.get("duration_minutes", 0) for s in sessions)

    def is_late_night_session(self) -> bool:
        """Check if current time is late night (10pm - 6am)"""
        hour = datetime.now().hour
        return hour >= 22 or hour < 6

    def get_late_night_sessions_this_week(self) -> int:
        """Count late night sessions in the past week"""
        sessions = self.get_sessions_this_week()
        return sum(1 for s in sessions if s.get("hour", 12) >= 22 or s.get("hour", 12) < 6)

    # ==================== DEPENDENCY DETECTION ====================

    def calculate_dependency_signals(self) -> Dict:
        """
        Calculate dependency warning signals based on usage patterns.

        Returns dict with:
        - sessions_today: count
        - sessions_this_week: count
        - late_night_sessions: count this week
        - minutes_today: total
        - is_escalating: bool (usage increasing over time)
        - dependency_score: 0-10 composite score
        - warnings: list of human-readable warnings
        """
        sessions_today = self.count_sessions_today()
        sessions_week = self.count_sessions_this_week()
        late_night = self.get_late_night_sessions_this_week()
        minutes_today = self.get_total_minutes_today()

        # Check if usage is escalating (compare this week to prior)
        two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        data = self._load_data()

        prior_week = [
            s
            for s in data.get("usage_sessions", [])
            if two_weeks_ago <= s.get("date", "") < week_ago
        ]
        is_escalating = sessions_week > len(prior_week) * 1.5 if prior_week else False

        # Calculate composite dependency score (0-10)
        score = 0.0
        warnings = []

        # Sessions today factor
        if sessions_today >= 7:
            score += 4.0
            warnings.append(f"You've started {sessions_today} sessions today")
        elif sessions_today >= 5:
            score += 2.5
            warnings.append(f"You've had {sessions_today} sessions today")
        elif sessions_today >= 3:
            score += 1.5

        # Minutes today factor
        if minutes_today >= 120:
            score += 2.0
            warnings.append(f"You've spent {minutes_today} minutes with me today")
        elif minutes_today >= 60:
            score += 1.0

        # Late night factor
        if late_night >= 3:
            score += 2.0
            warnings.append(f"You've had {late_night} late-night sessions this week")
        elif late_night >= 1:
            score += 1.0

        # Escalation factor
        if is_escalating:
            score += 1.5
            warnings.append("Your usage is increasing compared to last week")

        # Current late night bonus
        if self.is_late_night_session():
            score += 0.5

        return {
            "sessions_today": sessions_today,
            "sessions_this_week": sessions_week,
            "late_night_sessions": late_night,
            "minutes_today": minutes_today,
            "is_escalating": is_escalating,
            "dependency_score": min(score, 10.0),
            "warnings": warnings,
        }

    def should_enforce_cooldown(self) -> tuple[bool, str]:
        """
        Check if a cooldown should be enforced.

        Returns (should_cooldown, reason)
        """
        signals = self.calculate_dependency_signals()

        if signals["sessions_today"] >= 7:
            return (
                True,
                "You've had many sessions today. Please take a break and talk to someone you trust.",
            )

        if signals["minutes_today"] >= 120:
            return True, "You've spent a lot of time here today. Step away for a while."

        if signals["dependency_score"] >= 8:
            return (
                True,
                "Your usage pattern suggests you might be relying on me too much. Take a break.",
            )

        return False, ""

    # ==================== POLICY EVENT LOGGING ====================

    def log_policy_event(
        self, policy_type: str, domain: str, risk_weight: float, action_taken: str
    ):
        """
        Log when a safety policy fires (for transparency/audit).

        Args:
            policy_type: e.g., "domain_redirect", "crisis_stop", "dependency_intervention"
            domain: The detected domain
            risk_weight: The calculated risk weight
            action_taken: What the system did
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_policy_event(policy_type, domain, action_taken, risk_weight)

        # JSON backend
        data = self._load_data()

        if "policy_events" not in data:
            data["policy_events"] = []

        event = {
            "datetime": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "policy_type": policy_type,
            "domain": domain,
            "risk_weight": risk_weight,
            "action_taken": action_taken,
        }

        data["policy_events"].append(event)
        self._save_data(data)

        return event

    def get_recent_policy_events(self, limit: int = 10) -> List[Dict]:
        """Get recent policy events for transparency"""
        data = self._load_data()
        events = data.get("policy_events", [])
        return events[-limit:] if events else []

    # ==================== WELLNESS SUMMARY ====================

    def get_wellness_summary(self) -> Dict:
        """Get comprehensive summary of wellness patterns"""
        data = self._load_data()

        # Session stats
        sessions_today = self.count_sessions_today()
        sessions_week = self.count_sessions_this_week()
        minutes_today = self.get_total_minutes_today()

        # Check-in stats
        total_checkins = len(data.get("check_ins", []))

        if data.get("check_ins"):
            scores = [c["feeling_score"] for c in data["check_ins"]]
            avg_score = sum(scores) / len(scores)
            latest_checkin = data["check_ins"][-1]["date"]
        else:
            avg_score = 0
            latest_checkin = None

        # Dependency signals
        dependency = self.calculate_dependency_signals()

        return {
            "sessions_today": sessions_today,
            "sessions_this_week": sessions_week,
            "minutes_today": minutes_today,
            "total_sessions": len(data.get("usage_sessions", [])),
            "total_checkins": total_checkins,
            "average_feeling": round(avg_score, 1) if avg_score else None,
            "latest_checkin": latest_checkin,
            "dependency_score": dependency["dependency_score"],
            "dependency_warnings": dependency["warnings"],
            "should_take_break": dependency["dependency_score"] >= 5,
        }

    # ==================== DATA MANAGEMENT ====================

    def _load_data(self) -> Dict:
        """
        Load wellness data from the configured storage backend.

        When USE_SQLITE is enabled, loads from SQLite and converts to dict format.
        Otherwise, loads from JSON file with schema migration support.
        """
        # SQLite backend - reconstruct dict from database queries
        if self._backend is not None and settings.USE_SQLITE:
            return self._load_data_from_sqlite()

        # JSON backend (default)
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
            return self._migrate_schema(data)
        except FileNotFoundError:
            logger.info("Wellness data file not found, returning defaults")
            return self._get_default_data()
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted wellness data file: {e}")
            # Attempt recovery: backup corrupted file and return defaults
            self._backup_corrupted_file()
            return self._get_default_data()
        except Exception as e:
            logger.error(f"Unexpected error loading wellness data: {e}")
            return self._get_default_data()

    def _load_data_from_sqlite(self) -> Dict:
        """Load data from SQLite and convert to dict format for compatibility."""
        try:
            # Get data from SQLite via storage backend
            # We query with a wide date range to get all historical data
            far_past = date(2020, 1, 1)
            today = date.today()

            check_ins = self._backend.get_recent_check_ins(days=3650)  # ~10 years
            sessions = self._backend.get_sessions_for_period(far_past, today)
            policy_events = self._backend.get_recent_policy_events(limit=1000)
            intents = self._backend.get_session_intents_for_period(far_past, today)
            independence = self._backend.get_independence_records_for_period(far_past, today)
            handoffs = self._backend.get_handoff_events_for_period(far_past, today)
            self_reports = self._backend.get_recent_self_reports(limit=100)
            task_patterns = self._backend.get_all_task_patterns()

            # Convert to the dict format expected by existing code
            return {
                "schema_version": SCHEMA_VERSION,
                "check_ins": check_ins,
                "usage_sessions": sessions,
                "policy_events": policy_events,
                "session_intents": intents,
                "independence_records": independence,
                "handoff_events": handoffs,
                "self_reports": self_reports,
                "task_patterns": task_patterns,
                "created_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error loading from SQLite, falling back to JSON: {e}")
            # Fall back to JSON on error
            try:
                with open(self.data_file, "r") as f:
                    return json.load(f)
            except Exception:
                return self._get_default_data()

    def _migrate_schema(self, data: Dict) -> Dict:
        """Migrate data from older schema versions"""
        current_version = data.get("schema_version", 0)

        if current_version < SCHEMA_VERSION:
            logger.info(f"Migrating wellness data from v{current_version} to v{SCHEMA_VERSION}")

            # v0 -> v1: Add schema_version and ensure all fields exist
            if current_version < 1:
                data["schema_version"] = SCHEMA_VERSION
                defaults = self._get_default_data()
                for key in defaults:
                    if key not in data:
                        data[key] = defaults[key]

            # Future migrations would go here:
            # if current_version < 2:
            #     data = self._migrate_v1_to_v2(data)

            # Save migrated data
            self._save_data(data)

        return data

    def _backup_corrupted_file(self):
        """Backup a corrupted data file before overwriting"""
        if self.data_file.exists():
            backup_path = self.data_file.with_suffix(
                f".corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            try:
                self.data_file.rename(backup_path)
                logger.warning(f"Corrupted file backed up to: {backup_path}")
            except Exception as e:
                logger.error(f"Failed to backup corrupted file: {e}")

    def _save_data(self, data: Dict):
        """
        Save wellness data atomically using temp file + rename pattern.

        This ensures that an interrupted write never leaves a corrupted file:
        1. Write to temp file in same directory
        2. Flush and fsync to ensure data hits disk
        3. Atomic rename (os.replace) to target path
        """
        # Ensure schema version is set
        if "schema_version" not in data:
            data["schema_version"] = SCHEMA_VERSION

        # Ensure parent directory exists
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file, then atomic rename
        fd, temp_path = tempfile.mkstemp(
            dir=self.data_file.parent, prefix=".wellness_data_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename (POSIX guarantees atomicity on same filesystem)
            os.replace(temp_path, self.data_file)

        except Exception as e:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            logger.error(f"Failed to save wellness data: {e}")
            raise

    def clear_data(self):
        """Clear all wellness data (user-initiated)"""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            self._backend.clear_all_data()
            return

        self._save_data(self._get_default_data())

    def reset_all_data(self):
        """Reset ALL data - complete fresh start (user-initiated)"""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            self._backend.clear_all_data()
            return

        data = self._get_default_data()
        data["task_patterns"] = {}
        self._save_data(data)

    # ==================== SESSION INTENT CHECK-IN ====================

    def should_show_intent_check_in(self, first_message: str = "") -> bool:
        """
        Determine if we should show the "What brings you here?" check-in.

        Rules:
        - Don't show if first message is clearly practical (starts with imperative)
        - Show after min_sessions_between sessions without check-in
        - Always show if max_days_between days since last check-in
        """
        data = self._load_data()
        intents = data.get("session_intents", [])

        # Config defaults (could load from scenarios/intents/session_intents.yaml)
        min_sessions_between = 3
        max_days_between = 7

        # Skip if first message is clearly practical
        if first_message:
            practical_starters = [
                "write me",
                "write a",
                "help me write",
                "draft a",
                "draft me",
                "create a",
                "make me",
                "code for",
                "write code",
                "explain how",
                "show me how",
                "give me a",
                "template for",
                "list of",
            ]
            msg_lower = first_message.lower()
            if any(msg_lower.startswith(starter) for starter in practical_starters):
                return False

        if not intents:
            # First session ever - don't interrupt, let them discover naturally
            return False

        # Count sessions since last check-in
        sessions_since_checkin = 0
        last_checkin_date = None

        for intent_record in reversed(intents):
            if intent_record.get("was_check_in"):
                last_checkin_date = intent_record.get("date")
                break
            sessions_since_checkin += 1

        # Check if enough sessions have passed
        if sessions_since_checkin >= min_sessions_between:
            return True

        # Check if enough days have passed
        if last_checkin_date:
            try:
                last_date = datetime.fromisoformat(last_checkin_date).date()
                days_since = (date.today() - last_date).days
                if days_since >= max_days_between:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def record_session_intent(
        self, intent: str, was_check_in: bool = False, auto_detected: bool = False
    ) -> Dict:
        """
        Record the intent for this session.

        Args:
            intent: One of INTENT_PRACTICAL, INTENT_PROCESSING, INTENT_CONNECTION
            was_check_in: Whether this came from explicit user selection
            auto_detected: Whether this was auto-detected from message content
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_session_intent(intent, was_check_in, auto_detected)

        # JSON backend
        data = self._load_data()

        if "session_intents" not in data:
            data["session_intents"] = []

        record = {
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "intent": intent,
            "was_check_in": was_check_in,
            "auto_detected": auto_detected,
        }

        data["session_intents"].append(record)
        self._save_data(data)

        return record

    def get_connection_seeking_frequency(self, days: int = 30) -> Dict:
        """
        Analyze connection-seeking patterns over time.

        Returns frequency and trend data for anti-engagement metrics.
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        data = self._load_data()
        intents = data.get("session_intents", [])

        recent = [i for i in intents if i.get("date", "") >= cutoff]

        total = len(recent)
        connection_count = sum(1 for i in recent if i.get("intent") == INTENT_CONNECTION)
        practical_count = sum(1 for i in recent if i.get("intent") == INTENT_PRACTICAL)
        processing_count = sum(1 for i in recent if i.get("intent") == INTENT_PROCESSING)

        # Calculate ratio
        connection_ratio = connection_count / total if total > 0 else 0

        # Determine if this is a concern
        is_concerning = connection_ratio > 0.3 and connection_count >= 3

        return {
            "total_sessions": total,
            "connection_seeking": connection_count,
            "practical": practical_count,
            "processing": processing_count,
            "connection_ratio": round(connection_ratio, 2),
            "is_concerning": is_concerning,
            "days_analyzed": days,
        }

    def get_recent_intent(self) -> Optional[str]:
        """Get the most recent recorded session intent."""
        data = self._load_data()
        intents = data.get("session_intents", [])

        if intents:
            return intents[-1].get("intent")
        return None

    # ==================== TASK PATTERN TRACKING (GRADUATION) ====================

    def record_task_category(self, category: str) -> Dict:
        """
        Record when a task category is used (for graduation tracking).

        Args:
            category: e.g., 'email_drafting', 'code_help', 'explanations'

        Returns:
            Updated stats for this category
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            result = self._backend.record_task_pattern(category)
            # Convert to expected format
            return {
                "category": category,
                "count": result.get("count", 0),
                "last_7_days": result.get("last_7_days", 0),
                "last_30_days": result.get("last_30_days", 0),
                "first_use": result.get("first_use") or result.get("created_at"),
                "last_use": result.get("last_use") or result.get("last_seen"),
                "graduation_shown_count": result.get("graduation_shown_count", 0),
                "dismissal_count": result.get("dismissal_count", 0),
            }

        # JSON backend
        data = self._load_data()

        if "task_patterns" not in data:
            data["task_patterns"] = {}

        if category not in data["task_patterns"]:
            data["task_patterns"][category] = {
                "count": 0,
                "first_use": datetime.now().isoformat(),
                "uses": [],
                "graduation_shown_count": 0,
                "dismissal_count": 0,
            }

        pattern = data["task_patterns"][category]
        pattern["count"] += 1
        pattern["last_use"] = datetime.now().isoformat()
        pattern["uses"].append(
            {"datetime": datetime.now().isoformat(), "date": date.today().isoformat()}
        )

        # Keep only last 100 uses to prevent file bloat
        if len(pattern["uses"]) > 100:
            pattern["uses"] = pattern["uses"][-100:]

        self._save_data(data)

        # Return stats including recent count
        return self._get_category_stats(category, pattern)

    def _get_category_stats(self, category: str, pattern: Dict) -> Dict:
        """Calculate stats for a category."""
        uses = pattern.get("uses", [])

        # Count last 7 days
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        last_7_days = sum(1 for u in uses if u.get("date", "") >= week_ago)

        # Count last 30 days
        month_ago = (date.today() - timedelta(days=30)).isoformat()
        last_30_days = sum(1 for u in uses if u.get("date", "") >= month_ago)

        return {
            "category": category,
            "count": pattern.get("count", 0),
            "last_7_days": last_7_days,
            "last_30_days": last_30_days,
            "first_use": pattern.get("first_use"),
            "last_use": pattern.get("last_use"),
            "graduation_shown_count": pattern.get("graduation_shown_count", 0),
            "dismissal_count": pattern.get("dismissal_count", 0),
        }

    def get_task_patterns(self) -> Dict[str, Dict]:
        """
        Get usage stats for all tracked task categories.

        Returns:
            Dict mapping category name to stats
        """
        data = self._load_data()
        patterns = data.get("task_patterns", {})

        return {
            category: self._get_category_stats(category, pattern)
            for category, pattern in patterns.items()
        }

    def get_category_stats(self, category: str) -> Optional[Dict]:
        """Get stats for a specific category."""
        data = self._load_data()
        patterns = data.get("task_patterns", {})

        if category in patterns:
            return self._get_category_stats(category, patterns[category])
        return None

    def should_show_graduation_prompt(
        self,
        category: str,
        threshold: int,
        max_dismissals: int = 3,
        max_prompts_per_session: int = 1,
    ) -> Tuple[bool, str]:
        """
        Check if we should show a graduation prompt for this category.

        Args:
            category: The task category
            threshold: Number of uses before prompting
            max_dismissals: Stop suggesting after this many dismissals
            max_prompts_per_session: Max graduation prompts per session

        Returns:
            Tuple of (should_show, reason)
        """
        stats = self.get_category_stats(category)

        if not stats:
            return False, "no_data"

        # Check if user has dismissed too many times
        if stats["dismissal_count"] >= max_dismissals:
            return False, "max_dismissals_reached"

        # Check if threshold is met
        if stats["count"] < threshold:
            return False, "below_threshold"

        # Check if we've shown too recently (within last 3 uses)
        data = self._load_data()
        patterns = data.get("task_patterns", {})
        pattern = patterns.get(category, {})

        last_shown = pattern.get("last_graduation_shown")
        if last_shown:
            uses_since = stats["count"] - pattern.get("count_at_last_shown", 0)
            if uses_since < 3:
                return False, "shown_recently"

        # Check session limit (tracked in session state, not here)
        # The caller should track this

        return True, "threshold_met"

    def record_graduation_shown(self, category: str) -> None:
        """Record that we showed a graduation prompt for this category."""
        data = self._load_data()

        if "task_patterns" not in data or category not in data["task_patterns"]:
            return

        pattern = data["task_patterns"][category]
        pattern["graduation_shown_count"] = pattern.get("graduation_shown_count", 0) + 1
        pattern["last_graduation_shown"] = datetime.now().isoformat()
        pattern["count_at_last_shown"] = pattern.get("count", 0)

        self._save_data(data)

    def record_graduation_dismissal(self, category: str) -> None:
        """Record that user dismissed a graduation prompt."""
        data = self._load_data()

        if "task_patterns" not in data or category not in data["task_patterns"]:
            return

        pattern = data["task_patterns"][category]
        pattern["dismissal_count"] = pattern.get("dismissal_count", 0) + 1
        pattern["last_dismissal"] = datetime.now().isoformat()

        self._save_data(data)

    def record_graduation_accepted(self, category: str) -> None:
        """Record that user accepted skill tips."""
        data = self._load_data()

        if "task_patterns" not in data or category not in data["task_patterns"]:
            return

        pattern = data["task_patterns"][category]
        if "accepted_tips" not in pattern:
            pattern["accepted_tips"] = []

        pattern["accepted_tips"].append({"datetime": datetime.now().isoformat()})

        self._save_data(data)

    # ==================== INDEPENDENCE TRACKING ====================

    def record_independence(self, category: str = "general", notes: str = "") -> Dict:
        """
        Record when user reports completing a task independently.

        Args:
            category: Optional task category
            notes: Optional notes about what they did

        Returns:
            Independence record
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_independence_record(category, "", notes)

        # JSON backend
        data = self._load_data()

        if "independence_records" not in data:
            data["independence_records"] = []

        record = {
            "datetime": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "category": category,
            "notes": notes,
        }

        data["independence_records"].append(record)
        self._save_data(data)

        return record

    def get_independence_stats(self, days: int = 30) -> Dict:
        """
        Get independence tracking statistics.

        Returns count and trend data for celebrating user independence.
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        data = self._load_data()
        records = data.get("independence_records", [])

        recent = [r for r in records if r.get("date", "") >= cutoff]

        # Count by category
        by_category = {}
        for record in recent:
            cat = record.get("category", "general")
            by_category[cat] = by_category.get(cat, 0) + 1

        # Check for milestone
        total = len(recent)
        milestone_count = 5  # Could load from config
        is_milestone = total > 0 and total % milestone_count == 0

        return {
            "total_recent": total,
            "total_all_time": len(records),
            "by_category": by_category,
            "days_analyzed": days,
            "is_milestone": is_milestone,
        }

    def get_recent_independence(self, limit: int = 5) -> List[Dict]:
        """Get recent independence records."""
        data = self._load_data()
        records = data.get("independence_records", [])
        return records[-limit:] if records else []

    # ==================== HANDOFF TRACKING (PHASE 5) ====================

    def log_handoff_event(
        self,
        event_type: str,
        context: str = None,
        domain: str = None,
        outcome: str = None,
        details: Dict = None,
    ) -> Dict:
        """
        Log a handoff event for transparency and metrics.

        Args:
            event_type: 'initiated', 'reached_out', 'outcome_reported'
            context: Handoff context (e.g., 'after_difficult_task')
            domain: Conversation domain
            outcome: 'very_helpful', 'somewhat_helpful', 'not_helpful'
            details: Additional details

        Returns:
            The logged event
        """
        # Log as a policy event for transparency
        self.log_policy_event(
            policy_type=f"handoff_{event_type}",
            domain=domain or "general",
            risk_weight=0,
            action_taken=f"Handoff {event_type}: {context or 'general'}",
        )

        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            notes = json.dumps(details) if details else ""
            return self._backend.add_handoff_event(
                event_type, domain, context, outcome == "reached_out", notes
            )

        # JSON backend
        data = self._load_data()

        if "handoff_events" not in data:
            data["handoff_events"] = []

        event = {
            "datetime": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "event_type": event_type,
            "context": context,
            "domain": domain,
            "outcome": outcome,
            "details": details,
        }

        data["handoff_events"].append(event)

        # Keep last 200 events
        if len(data["handoff_events"]) > 200:
            data["handoff_events"] = data["handoff_events"][-200:]

        self._save_data(data)
        return event

    def get_handoff_success_metrics(self, days: int = 30) -> Dict:
        """
        Calculate handoff success metrics.

        Success = users reaching out to humans and finding it helpful.

        Returns:
            Dict with success metrics
        """
        data = self._load_data()
        events = data.get("handoff_events", [])

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        recent = [e for e in events if e.get("date", "") >= cutoff]

        # Count by event type
        initiated = sum(1 for e in recent if e.get("event_type") == "initiated")
        reached_out = sum(1 for e in recent if e.get("event_type") == "reached_out")
        outcome_reported = sum(1 for e in recent if e.get("event_type") == "outcome_reported")

        # Count outcomes
        outcomes = [e for e in recent if e.get("outcome")]
        very_helpful = sum(1 for e in outcomes if e.get("outcome") == "very_helpful")
        somewhat_helpful = sum(1 for e in outcomes if e.get("outcome") == "somewhat_helpful")
        not_helpful = sum(1 for e in outcomes if e.get("outcome") == "not_helpful")

        # Calculate success rate
        total_outcomes = very_helpful + somewhat_helpful + not_helpful
        helpful_rate = (
            (very_helpful + somewhat_helpful) / total_outcomes if total_outcomes > 0 else 0
        )

        # Calculate reach out rate
        reach_out_rate = reached_out / initiated if initiated > 0 else 0

        return {
            "period_days": days,
            "handoffs_initiated": initiated,
            "handoffs_completed": reached_out,
            "reach_out_rate": round(reach_out_rate, 2),
            "outcomes": {
                "very_helpful": very_helpful,
                "somewhat_helpful": somewhat_helpful,
                "not_helpful": not_helpful,
            },
            "helpful_rate": round(helpful_rate, 2),
            "is_healthy": reach_out_rate >= 0.3 and helpful_rate >= 0.5,
        }

    def should_show_handoff_follow_up(self) -> Tuple[bool, Optional[Dict]]:
        """
        Check if we should show a handoff follow-up prompt.

        Returns:
            Tuple of (should_show, pending_handoff_info)
        """
        data = self._load_data()
        events = data.get("handoff_events", [])

        # Find initiated handoffs without follow-up
        for event in reversed(events):  # Check most recent first
            if event.get("event_type") == "initiated" and not event.get("follow_up_shown"):
                # Check if enough time has passed (24 hours)
                event_time = datetime.fromisoformat(event["datetime"])
                if datetime.now() - event_time >= timedelta(hours=24):
                    return True, event

        return False, None

    def mark_handoff_follow_up_shown(self, event_datetime: str) -> None:
        """Mark a handoff event's follow-up as shown."""
        data = self._load_data()
        events = data.get("handoff_events", [])

        for event in events:
            if event.get("datetime") == event_datetime:
                event["follow_up_shown"] = True
                event["follow_up_shown_date"] = datetime.now().isoformat()
                self._save_data(data)
                return

    # ==================== PHASE 7: SUCCESS METRICS ====================

    # Sensitive domains that count toward anti-engagement score
    SENSITIVE_DOMAINS = {
        "relationships",
        "health",
        "money",
        "spirituality",
        "crisis",
        "harmful",
        "emotional",
    }

    def get_sensitive_usage_stats(self, days: int = 7) -> Dict:
        """
        Get usage stats for SENSITIVE topics only.

        Practical task usage is excluded - that's just using a tool.

        Returns:
            Dict with sensitive session counts and domain breakdown
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        data = self._load_data()

        # Get policy events (these track domain hits)
        events = data.get("policy_events", [])
        recent = [e for e in events if e.get("date", "") >= cutoff]

        # Count sensitive domain events
        sensitive_count = 0
        domain_breakdown = {}
        for event in recent:
            domain = event.get("domain", "")
            if domain in self.SENSITIVE_DOMAINS:
                sensitive_count += 1
                domain_breakdown[domain] = domain_breakdown.get(domain, 0) + 1

        # Get connection-seeking count from intents
        intents = data.get("session_intents", [])
        recent_intents = [i for i in intents if i.get("date", "") >= cutoff]
        connection_count = sum(1 for i in recent_intents if i.get("intent") == INTENT_CONNECTION)

        # Get late-night sensitive sessions
        late_night_sensitive = sum(
            1
            for e in recent
            if e.get("domain", "") in self.SENSITIVE_DOMAINS
            and self._is_late_night_hour(e.get("datetime", ""))
        )

        # Total sessions for ratio calculation
        sessions = data.get("usage_sessions", [])
        recent_sessions = [s for s in sessions if s.get("date", "") >= cutoff]
        total_sessions = len(recent_sessions)

        return {
            "period_days": days,
            "sensitive_sessions": sensitive_count,
            "connection_seeking": connection_count,
            "late_night_sensitive": late_night_sensitive,
            "total_sessions": total_sessions,
            "sensitive_ratio": sensitive_count / total_sessions if total_sessions > 0 else 0,
            "domain_breakdown": domain_breakdown,
        }

    def _is_late_night_hour(self, datetime_str: str) -> bool:
        """Check if a datetime string is during late-night hours (10PM-6AM)."""
        try:
            dt = datetime.fromisoformat(datetime_str)
            return dt.hour >= 22 or dt.hour < 6
        except (ValueError, TypeError):
            return False

    def get_weekly_comparison(self) -> Dict:
        """
        Compare this week's sensitive usage to last week.

        Returns trend direction and percentage change.
        """
        this_week = self.get_sensitive_usage_stats(days=7)
        last_week = self._get_sensitive_stats_for_period(start_days_ago=14, end_days_ago=7)

        # Calculate changes
        sensitive_change = self._calculate_change(
            this_week["sensitive_sessions"], last_week["sensitive_sessions"]
        )
        connection_change = self._calculate_change(
            this_week["connection_seeking"], last_week["connection_seeking"]
        )

        # Get human reach-outs comparison
        this_week_handoffs = self._count_handoffs_completed(days=7)
        last_week_handoffs = self._count_handoffs_completed_period(
            start_days_ago=14, end_days_ago=7
        )
        handoff_change = self._calculate_change(this_week_handoffs, last_week_handoffs)

        # Get independence comparison
        this_week_independence = len(self._get_independence_for_period(days=7))
        last_week_independence = len(
            self._get_independence_for_period_range(start_days_ago=14, end_days_ago=7)
        )
        independence_change = self._calculate_change(this_week_independence, last_week_independence)

        # Determine overall trend for sensitive usage (down is good)
        if sensitive_change < -0.15:
            sensitive_trend = "improving"
        elif sensitive_change > 0.15:
            sensitive_trend = "concerning"
        else:
            sensitive_trend = "stable"

        return {
            "this_week": {
                "sensitive_sessions": this_week["sensitive_sessions"],
                "connection_seeking": this_week["connection_seeking"],
                "human_reach_outs": this_week_handoffs,
                "independence": this_week_independence,
                "total_sessions": this_week["total_sessions"],
            },
            "last_week": {
                "sensitive_sessions": last_week["sensitive_sessions"],
                "connection_seeking": last_week["connection_seeking"],
                "human_reach_outs": last_week_handoffs,
                "independence": last_week_independence,
                "total_sessions": last_week["total_sessions"],
            },
            "changes": {
                "sensitive_sessions": round(sensitive_change, 2),
                "connection_seeking": round(connection_change, 2),
                "human_reach_outs": round(handoff_change, 2),
                "independence": round(independence_change, 2),
            },
            "sensitive_trend": sensitive_trend,
        }

    def _get_sensitive_stats_for_period(self, start_days_ago: int, end_days_ago: int) -> Dict:
        """Get sensitive usage stats for a specific period."""
        start_date = (date.today() - timedelta(days=start_days_ago)).isoformat()
        end_date = (date.today() - timedelta(days=end_days_ago)).isoformat()

        data = self._load_data()
        events = data.get("policy_events", [])
        period_events = [e for e in events if start_date <= e.get("date", "") < end_date]

        sensitive_count = sum(
            1 for e in period_events if e.get("domain", "") in self.SENSITIVE_DOMAINS
        )

        intents = data.get("session_intents", [])
        period_intents = [i for i in intents if start_date <= i.get("date", "") < end_date]
        connection_count = sum(1 for i in period_intents if i.get("intent") == INTENT_CONNECTION)

        sessions = data.get("usage_sessions", [])
        period_sessions = [s for s in sessions if start_date <= s.get("date", "") < end_date]

        return {
            "sensitive_sessions": sensitive_count,
            "connection_seeking": connection_count,
            "total_sessions": len(period_sessions),
        }

    def _calculate_change(self, current: int, previous: int) -> float:
        """Calculate percentage change between two values."""
        if previous == 0:
            return 1.0 if current > 0 else 0.0
        return (current - previous) / previous

    def _count_handoffs_completed(self, days: int) -> int:
        """Count handoffs marked as 'reached_out' in the given period."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        data = self._load_data()
        events = data.get("handoff_events", [])
        return sum(
            1
            for e in events
            if e.get("date", "") >= cutoff and e.get("event_type") == "reached_out"
        )

    def _count_handoffs_completed_period(self, start_days_ago: int, end_days_ago: int) -> int:
        """Count handoffs in a specific period."""
        start_date = (date.today() - timedelta(days=start_days_ago)).isoformat()
        end_date = (date.today() - timedelta(days=end_days_ago)).isoformat()
        data = self._load_data()
        events = data.get("handoff_events", [])
        return sum(
            1
            for e in events
            if start_date <= e.get("date", "") < end_date and e.get("event_type") == "reached_out"
        )

    def _get_independence_for_period(self, days: int) -> List[Dict]:
        """Get independence records for a period."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        data = self._load_data()
        records = data.get("independence_records", [])
        return [r for r in records if r.get("date", "") >= cutoff]

    def _get_independence_for_period_range(
        self, start_days_ago: int, end_days_ago: int
    ) -> List[Dict]:
        """Get independence records for a specific period range."""
        start_date = (date.today() - timedelta(days=start_days_ago)).isoformat()
        end_date = (date.today() - timedelta(days=end_days_ago)).isoformat()
        data = self._load_data()
        records = data.get("independence_records", [])
        return [r for r in records if start_date <= r.get("date", "") < end_date]

    def calculate_anti_engagement_score(self) -> Dict:
        """
        Calculate anti-engagement score based on SENSITIVE topic usage.

        Score is 0-10. Lower = healthier relationship with AI.
        Only sensitive topics count - practical task usage is ignored.

        Returns:
            Dict with score, factors breakdown, and interpretation
        """
        # Get sensitive usage stats
        sensitive_7d = self.get_sensitive_usage_stats(days=7)
        sensitive_30d = self.get_sensitive_usage_stats(days=30)

        # Factor 1: Sensitive sessions per week (weight 0.35)
        # Thresholds calibrated to avoid being overly dramatic:
        # - 10+/week = daily habit, concerning
        # - 7-9 = frequent, worth monitoring
        # - 4-6 = moderate, normal for someone working through something
        # - 1-3 = occasional, healthy usage
        sensitive_sessions = sensitive_7d["sensitive_sessions"]
        if sensitive_sessions >= 10:
            factor_sensitive = 10.0
        elif sensitive_sessions >= 7:
            factor_sensitive = 6.0
        elif sensitive_sessions >= 4:
            factor_sensitive = 3.0
        elif sensitive_sessions >= 1:
            factor_sensitive = 1.0
        else:
            factor_sensitive = 0.0

        # Factor 2: Connection-seeking ratio (weight 0.25)
        connection_ratio = sensitive_7d["connection_seeking"] / max(
            sensitive_7d["total_sessions"], 1
        )
        if connection_ratio >= 0.3:
            factor_connection = 10.0
        elif connection_ratio >= 0.2:
            factor_connection = 7.0
        elif connection_ratio >= 0.1:
            factor_connection = 4.0
        else:
            factor_connection = 0.0

        # Factor 3: Late-night sensitive ratio (weight 0.20)
        late_night_ratio = sensitive_7d["late_night_sensitive"] / max(
            sensitive_7d["sensitive_sessions"], 1
        )
        if late_night_ratio >= 0.3:
            factor_late_night = 10.0
        elif late_night_ratio >= 0.2:
            factor_late_night = 6.0
        elif late_night_ratio >= 0.1:
            factor_late_night = 3.0
        else:
            factor_late_night = 0.0

        # Factor 4: Week-over-week escalation (weight 0.20)
        # Only penalize if there's a meaningful baseline to compare against
        # If last week was 0, this is the user's first week - don't penalize
        comparison = self.get_weekly_comparison()
        last_week_sensitive = comparison.get("last_week", {}).get("sensitive_sessions", 0)
        escalation = comparison["changes"]["sensitive_sessions"]

        if last_week_sensitive == 0:
            # No baseline - don't penalize for "escalation"
            factor_escalation = 0.0
        elif escalation >= 0.5:  # 50% increase
            factor_escalation = 10.0
        elif escalation >= 0.3:  # 30% increase
            factor_escalation = 6.0
        elif escalation >= 0.15:  # 15% increase
            factor_escalation = 3.0
        else:
            factor_escalation = 0.0

        # Calculate weighted score
        score = (
            factor_sensitive * 0.35
            + factor_connection * 0.25
            + factor_late_night * 0.20
            + factor_escalation * 0.20
        )
        score = min(score, 10.0)

        # Determine interpretation
        if score <= 2:
            level = "excellent"
            label = "Healthy Balance"
            message = (
                "You're using this tool appropriately and keeping personal matters with humans."
            )
        elif score <= 4:
            level = "good"
            label = "On Track"
            message = "You're generally keeping sensitive topics for human conversations."
        elif score <= 6:
            level = "moderate"
            label = "Worth Monitoring"
            message = "You're bringing sensitive topics here more than ideal. Consider human conversations."
        elif score <= 8:
            level = "concerning"
            label = "High Reliance"
            message = "You're relying on AI for personal/emotional topics. Please talk to someone you trust."
        else:
            level = "high"
            label = "Please Reach Out"
            message = "Your pattern suggests you're using AI as a substitute for human connection. This isn't healthy."

        # Get 30-day trend
        sensitive_30d_weekly = sensitive_30d["sensitive_sessions"] / 4  # Avg per week
        if sensitive_7d["sensitive_sessions"] < sensitive_30d_weekly * 0.85:
            trend = "improving"
            trend_message = "You're bringing fewer sensitive topics to AI. That's healthy growth."
        elif sensitive_7d["sensitive_sessions"] > sensitive_30d_weekly * 1.15:
            trend = "increasing"
            trend_message = (
                "You're bringing more personal topics here. Consider human conversations instead."
            )
        else:
            trend = "stable"
            trend_message = "Your sensitive topic usage is stable."

        return {
            "score": round(score, 1),
            "level": level,
            "label": label,
            "message": message,
            "factors": {
                "sensitive_sessions": {
                    "value": sensitive_sessions,
                    "score": round(factor_sensitive, 1),
                    "weight": 0.35,
                },
                "connection_seeking": {
                    "value": round(connection_ratio, 2),
                    "score": round(factor_connection, 1),
                    "weight": 0.25,
                },
                "late_night": {
                    "value": round(late_night_ratio, 2),
                    "score": round(factor_late_night, 1),
                    "weight": 0.20,
                },
                "escalation": {
                    "value": round(escalation, 2),
                    "score": round(factor_escalation, 1),
                    "weight": 0.20,
                },
            },
            "trend": trend,
            "trend_message": trend_message,
        }

    def get_my_patterns_dashboard(self) -> Dict:
        """
        Get complete dashboard data for "My Patterns" view.

        Separates sensitive vs practical usage and provides week-over-week
        comparison with appropriate messaging.
        """
        comparison = self.get_weekly_comparison()
        anti_engagement = self.calculate_anti_engagement_score()

        # Get practical task stats (for context, not judged)
        task_patterns = self.get_task_patterns()
        practical_tasks_week = sum(p.get("last_7_days", 0) for p in task_patterns.values())

        # Determine overall health message
        if anti_engagement["score"] <= 4 and comparison["this_week"]["human_reach_outs"] >= 1:
            health_status = "healthy"
            summary = "Your patterns look healthy. You're using empathySync for practical tasks and keeping personal matters with humans."
        elif anti_engagement["score"] >= 6 or comparison["sensitive_trend"] == "concerning":
            health_status = "concerning"
            summary = "You're bringing more sensitive topics here than usual. Consider reaching out to someone you trust."
        else:
            health_status = "moderate"
            summary = "Your usage is moderate. Keep an eye on how much you're bringing personal topics here."

        return {
            "this_week": {
                "sensitive_topics": comparison["this_week"]["sensitive_sessions"],
                "connection_seeking": comparison["this_week"]["connection_seeking"],
                "human_reach_outs": comparison["this_week"]["human_reach_outs"],
                "did_it_myself": comparison["this_week"]["independence"],
                "practical_tasks": practical_tasks_week,
                "total_sessions": comparison["this_week"]["total_sessions"],
            },
            "last_week": {
                "sensitive_topics": comparison["last_week"]["sensitive_sessions"],
                "connection_seeking": comparison["last_week"]["connection_seeking"],
                "human_reach_outs": comparison["last_week"]["human_reach_outs"],
                "did_it_myself": comparison["last_week"]["independence"],
            },
            "trends": {
                "sensitive_topics": self._trend_indicator(
                    comparison["changes"]["sensitive_sessions"], invert=True
                ),
                "connection_seeking": self._trend_indicator(
                    comparison["changes"]["connection_seeking"], invert=True
                ),
                "human_reach_outs": self._trend_indicator(
                    comparison["changes"]["human_reach_outs"]
                ),
                "did_it_myself": self._trend_indicator(comparison["changes"]["independence"]),
            },
            "anti_engagement": anti_engagement,
            "health_status": health_status,
            "summary": summary,
            "practical_note": "Practical task usage is fine - that's just using a tool.",
        }

    def _trend_indicator(self, change: float, invert: bool = False) -> Dict:
        """
        Get trend indicator for a metric.

        Args:
            change: Percentage change (positive = increase)
            invert: If True, decrease is good (for sensitive metrics)
        """
        if invert:
            # For sensitive metrics: decrease is good
            if change < -0.15:
                return {"icon": "↓", "status": "improving", "label": "Down"}
            elif change > 0.15:
                return {"icon": "↑", "status": "concerning", "label": "Up"}
            else:
                return {"icon": "→", "status": "stable", "label": "Stable"}
        else:
            # For positive metrics: increase is good
            if change > 0.15:
                return {"icon": "↑", "status": "improving", "label": "Up"}
            elif change < -0.15:
                return {"icon": "↓", "status": "concerning", "label": "Down"}
            else:
                return {"icon": "→", "status": "stable", "label": "Stable"}

    # ==================== SELF-REPORT TRACKING (7.2) ====================

    def should_show_self_report(self) -> Tuple[bool, Optional[Dict]]:
        """
        Check if we should show a self-report prompt.

        Respects frequency limits: max 1 per week, min 5 days between.

        Returns:
            Tuple of (should_show, prompt_config)
        """
        data = self._load_data()
        self_reports = data.get("self_reports", [])

        # Check if we've shown a report recently
        if self_reports:
            last_report = self_reports[-1]
            last_date = last_report.get("date", "")
            if last_date:
                days_since = (date.today() - date.fromisoformat(last_date)).days
                if days_since < 5:
                    return False, None

        # Check for pending triggers
        # 1. After handoff (24+ hours)
        should_show, handoff = self.should_show_handoff_follow_up()
        if should_show:
            return True, {
                "type": "handoff_followup",
                "question": "Did talking to someone help?",
                "options": [
                    {"label": "Yes, it helped", "value": "helpful"},
                    {"label": "Not really", "value": "not_helpful"},
                    {"label": "Skip", "value": "skip"},
                ],
                "handoff_context": handoff,
            }

        # 2. High usage week check
        comparison = self.get_weekly_comparison()
        if comparison["this_week"]["sensitive_sessions"] >= 5:
            return True, {
                "type": "usage_reflection",
                "question": "You've brought personal topics here often this week. How are you feeling about that?",
                "options": [
                    {"label": "It's been helpful", "value": "helpful"},
                    {"label": "Maybe too much", "value": "too_much"},
                    {"label": "Not sure", "value": "unsure"},
                    {"label": "Skip", "value": "skip"},
                ],
            }

        return False, None

    def record_self_report(self, report_type: str, response: str, details: Dict = None) -> Dict:
        """
        Record a self-report response.

        Args:
            report_type: 'handoff_followup', 'weekly_clarity', 'usage_reflection'
            response: The user's response value
            details: Optional additional context
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            content = json.dumps({"response": response, "details": details})
            return self._backend.add_self_report(report_type, content)

        # JSON backend
        data = self._load_data()

        if "self_reports" not in data:
            data["self_reports"] = []

        report = {
            "datetime": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "type": report_type,
            "response": response,
            "details": details,
        }

        data["self_reports"].append(report)

        # Keep last 100 reports
        if len(data["self_reports"]) > 100:
            data["self_reports"] = data["self_reports"][-100:]

        self._save_data(data)
        return report

    def get_self_report_history(self, limit: int = 10) -> List[Dict]:
        """Get recent self-report responses."""
        data = self._load_data()
        reports = data.get("self_reports", [])
        return reports[-limit:] if reports else []
