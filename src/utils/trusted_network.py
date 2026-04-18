"""
Trusted Network - Local storage and management of user's trusted humans

This module helps users identify, remember, and reach out to
the real humans in their life. All data stays local.

Supports two storage backends:
- JSON files (default, backward compatible)
- SQLite database (when USE_SQLITE=true, better for multi-device sync)
"""

import json
import os
import tempfile
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional
import random

from config.settings import settings
from utils.scenario_loader import get_scenario_loader

logger = logging.getLogger(__name__)


def _get_storage_backend():
    """Lazy import to avoid circular dependency."""
    if settings.USE_SQLITE:
        from utils.storage_backend import get_storage_backend

        return get_storage_backend()
    return None


# Schema version for data migration support
SCHEMA_VERSION = 1


class TrustedNetwork:
    """
    Manages the user's network of trusted humans.

    Helps answer the question: "Who in your life could you talk to about this?"
    All data stored locally. No external calls.

    Supports two storage backends:
    - JSON files (default)
    - SQLite database (when settings.USE_SQLITE is True)
    """

    def __init__(self):
        self.data_file = settings.DATA_DIR / "trusted_network.json"
        self.loader = get_scenario_loader()
        self._backend = _get_storage_backend()
        self._ensure_data_file()

    def _ensure_data_file(self):
        """Ensure data file exists with current schema."""
        if not self.data_file.exists():
            self._save_data(self._get_default_data())

    def _get_default_data(self) -> Dict:
        """Return default data structure with current schema version."""
        return {
            "schema_version": SCHEMA_VERSION,
            "people": [],
            "reach_outs": [],
            "created_at": datetime.now().isoformat(),
        }

    def _load_data(self) -> Dict:
        """Load network data from file with schema migration support."""
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
            return self._migrate_schema(data)
        except FileNotFoundError:
            logger.info("Trusted network file not found, returning defaults")
            return self._get_default_data()
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted trusted network file: {e}")
            self._backup_corrupted_file()
            return self._get_default_data()
        except Exception as e:
            logger.error(f"Unexpected error loading trusted network: {e}")
            return self._get_default_data()

    def _migrate_schema(self, data: Dict) -> Dict:
        """Migrate data from older schema versions."""
        current_version = data.get("schema_version", 0)

        if current_version < SCHEMA_VERSION:
            logger.info(f"Migrating trusted network from v{current_version} to v{SCHEMA_VERSION}")

            # v0 -> v1: Add schema_version and ensure all fields exist
            if current_version < 1:
                data["schema_version"] = SCHEMA_VERSION
                defaults = self._get_default_data()
                for key in defaults:
                    if key not in data:
                        data[key] = defaults[key]

            self._save_data(data)

        return data

    def _backup_corrupted_file(self):
        """Backup a corrupted data file before overwriting."""
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
        Save network data atomically using temp file + rename pattern.

        This ensures that an interrupted write never leaves a corrupted file.
        """
        # Ensure schema version is set
        if "schema_version" not in data:
            data["schema_version"] = SCHEMA_VERSION

        # Ensure parent directory exists
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file, then atomic rename
        fd, temp_path = tempfile.mkstemp(
            dir=self.data_file.parent, prefix=".trusted_network_", suffix=".tmp"
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
            logger.error(f"Failed to save trusted network: {e}")
            raise

    # ==================== MANAGING TRUSTED PEOPLE ====================

    def add_person(
        self,
        name: str,
        relationship: str = "",
        contact: str = "",
        notes: str = "",
        domains: List[str] = None,
    ) -> Dict:
        """
        Add a trusted person to the network.

        Args:
            name: Their name
            relationship: e.g., "friend", "sister", "mentor", "therapist"
            contact: Phone number, email, or how to reach them
            notes: Any notes about this person
            domains: Topics they're good for (e.g., ["money", "relationships"])
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.add_trusted_person(name, relationship, contact, notes, domains)

        # JSON backend
        data = self._load_data()

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
        self._save_data(data)

        return person

    def get_all_people(self) -> List[Dict]:
        """Get all trusted people."""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.get_all_trusted_people()

        data = self._load_data()
        return data.get("people", [])

    def get_person_by_name(self, name: str) -> Optional[Dict]:
        """Find a person by name (case-insensitive partial match)."""
        people = self.get_all_people()
        name_lower = name.lower()
        for person in people:
            if name_lower in person["name"].lower():
                return person
        return None

    def get_people_for_domain(self, domain: str) -> List[Dict]:
        """Get people suited for a particular topic/domain."""
        people = self.get_all_people()
        matches = [p for p in people if domain in p.get("domains", [])]

        # If no specific matches, return all people
        if not matches:
            return people

        return matches

    def update_person(self, person_id: int, updates: Dict) -> Optional[Dict]:
        """Update a person's information."""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.update_trusted_person(person_id, updates)

        # JSON backend
        data = self._load_data()

        for person in data["people"]:
            if person["id"] == person_id:
                person.update(updates)
                self._save_data(data)
                return person

        return None

    def remove_person(self, person_id: int) -> bool:
        """Remove a person from the network."""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            return self._backend.remove_trusted_person(person_id)

        # JSON backend
        data = self._load_data()
        original_count = len(data["people"])
        data["people"] = [p for p in data["people"] if p["id"] != person_id]

        if len(data["people"]) < original_count:
            self._save_data(data)
            return True
        return False

    # ==================== TRACKING REACH OUTS ====================

    def log_reach_out(
        self, person_name: str, method: str = "unknown", topic: str = "", notes: str = ""
    ):
        """
        Log when user reaches out to someone.

        This is a success metric - we want to see this increase.
        """
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            # Find person_id by name
            people = self._backend.get_all_trusted_people()
            person_id = None
            for person in people:
                if person["name"].lower() == person_name.lower():
                    person_id = person["id"]
                    break
            return self._backend.add_reach_out(person_id, person_name, method, notes)

        # JSON backend
        data = self._load_data()

        reach_out = {
            "date": date.today().isoformat(),
            "datetime": datetime.now().isoformat(),
            "person_name": person_name,
            "method": method,  # call, text, in-person, etc.
            "topic": topic,
            "notes": notes,
        }

        data["reach_outs"].append(reach_out)

        # Update last_contact for this person
        for person in data["people"]:
            if person["name"].lower() == person_name.lower():
                person["last_contact"] = date.today().isoformat()

        self._save_data(data)
        return reach_out

    def get_recent_reach_outs(self, days: int = 30) -> List[Dict]:
        """Get reach outs from the last N days."""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            from datetime import timedelta

            start_date = date.today() - timedelta(days=days)
            return self._backend.get_reach_outs_for_period(start_date)

        # JSON backend
        data = self._load_data()
        cutoff = (datetime.now().date() - __import__("datetime").timedelta(days=days)).isoformat()

        return [r for r in data.get("reach_outs", []) if r.get("date", "") >= cutoff]

    def count_reach_outs_this_week(self) -> int:
        """Count reach outs in the past 7 days."""
        return len(self.get_recent_reach_outs(7))

    def get_neglected_contacts(self, days: int = 30) -> List[Dict]:
        """Get people you haven't contacted in a while."""
        people = self.get_all_people()
        cutoff = (datetime.now().date() - __import__("datetime").timedelta(days=days)).isoformat()

        neglected = []
        for person in people:
            last = person.get("last_contact")
            if not last or last < cutoff:
                neglected.append(person)

        return neglected

    # ==================== PROMPTS AND SUGGESTIONS ====================

    def get_setup_prompt(self) -> str:
        """Get a prompt to help user set up their trusted network."""
        prompts = self.loader.get_all_prompts().get("human_connection", {})
        setup_prompts = prompts.get("trusted_network_prompts", {}).get("initial_setup", [])

        if setup_prompts:
            return random.choice(setup_prompts)
        return "Who are 2-3 people in your life you could call if things got hard?"

    def get_reflection_prompt(self) -> str:
        """Get a prompt for reflecting on relationships."""
        prompts = self.loader.get_all_prompts().get("human_connection", {})
        reflection = prompts.get("trusted_network_prompts", {}).get("reflection", [])

        if reflection:
            return random.choice(reflection)
        return "When did you last have a real conversation with someone you trust?"

    def get_domain_prompt(self, domain: str) -> str:
        """Get a prompt specific to a domain."""
        prompts = self.loader.get_all_prompts().get("human_connection", {})
        by_domain = prompts.get("trusted_network_prompts", {}).get("prompts_by_domain", {})

        domain_prompts = by_domain.get(domain, by_domain.get("general", []))

        if domain_prompts:
            return random.choice(domain_prompts)
        return "Who in your life could you talk to about this?"

    def get_reach_out_template(self, situation: str = "need_to_talk", name: str = None) -> Dict:
        """
        Get a template for reaching out.

        Args:
            situation: One of "reconnecting", "need_to_talk", "checking_in",
                      "hard_conversation", "asking_for_help", "after_argument", "gratitude"
            name: Optional person's name to interpolate into the opening greeting.
                  "Hey, I've been..." becomes "Hey Sarah, I've been..."
        """
        prompts = self.loader.get_all_prompts().get("human_connection", {})
        templates = prompts.get("reach_out_templates", {})

        if situation in templates:
            template_group = templates[situation]
            text = random.choice(template_group.get("templates", []))
        else:
            text = "Hey, I've been thinking about you. Could we talk sometime?"
            template_group = {}

        if name:
            text = text.replace("Hey,", f"Hey {name},", 1).replace("Hi.", f"Hi {name}.", 1)

        return {
            "name": template_group.get("name", situation) if template_group else "Reaching out",
            "template": text,
        }

    def get_exit_celebration(self, chose_human: bool = True) -> str:
        """Get an exit celebration message."""
        prompts = self.loader.get_all_prompts().get("human_connection", {})
        celebrations = prompts.get("exit_celebrations", {})

        if chose_human:
            messages = celebrations.get("chose_human", [])
        else:
            messages = celebrations.get("ending_session", [])

        if messages:
            return random.choice(messages)
        return "You're choosing human connection. That's the point."

    # Relationship types considered relevant per domain for ranking purposes
    _DOMAIN_RELATIONSHIP_KEYWORDS = {
        "emotional": [
            "therapist",
            "counselor",
            "psychologist",
            "partner",
            "spouse",
            "friend",
            "sibling",
            "brother",
            "sister",
        ],
        "health": ["therapist", "counselor", "doctor", "nurse", "partner", "spouse"],
        "money": ["mentor", "advisor", "accountant", "financial"],
        "relationships": [
            "therapist",
            "counselor",
            "partner",
            "spouse",
            "parent",
            "mom",
            "dad",
            "mother",
            "father",
            "sibling",
            "friend",
        ],
        "spirituality": ["pastor", "priest", "imam", "rabbi", "mentor", "spiritual"],
        "logistics": ["mentor", "colleague", "coworker", "friend"],
    }

    def _score_person_for_domain(self, person: Dict, domain: str) -> tuple:
        """
        Score a person's relevance for a domain.

        Returns (score, suggestion_reason) where higher score = better match.
        Scoring:
          +3  explicit domain tag matches
          +1  relationship type is relevant to domain
          +2  contacted within 7 days (warm connection)
          +1  contacted within 30 days
        """
        score = 0
        reason = person.get("relationship", "")

        # Explicit domain match
        if domain in person.get("domains", []):
            score += 3

        # Relationship type relevance
        rel = person.get("relationship", "").lower()
        relevant_rels = self._DOMAIN_RELATIONSHIP_KEYWORDS.get(domain, [])
        if any(kw in rel for kw in relevant_rels):
            score += 1

        # Recency
        last_contact = person.get("last_contact")
        if last_contact:
            try:
                from datetime import date as _date, timedelta

                last_date = _date.fromisoformat(last_contact)
                days_since = (_date.today() - last_date).days
                if days_since <= 7:
                    score += 2
                    label = "day" if days_since == 1 else "days"
                    reason = f"Spoke {days_since} {label} ago"
                elif days_since <= 30:
                    score += 1
                else:
                    reason = f"Haven't connected in {days_since} days"
            except ValueError:
                pass

        return score, reason

    def suggest_person_for_domain(self, domain: str) -> Optional[Dict]:
        """
        Suggest the most relevant person for a given domain.

        Ranks candidates by domain match, relationship type relevance, and
        recency of contact. Among equally scored candidates, picks randomly.
        Returns the person dict with an extra `suggestion_reason` key.
        """
        people = self.get_people_for_domain(domain)
        if not people:
            return None

        scored = []
        for person in people:
            score, reason = self._score_person_for_domain(person, domain)
            scored.append((score, person, reason))

        scored.sort(key=lambda x: x[0], reverse=True)

        top_score = scored[0][0]
        top_group = [s for s in scored if s[0] == top_score]
        _, best_person, reason = random.choice(top_group)

        return {**best_person, "suggestion_reason": reason}

    # ==================== CONNECTION BUILDING (PHASE 12) ====================

    def is_network_empty(self) -> bool:
        """Check if the trusted network is empty."""
        return len(self.get_all_people()) == 0

    def get_signposts(self, domain: str = None) -> Dict:
        """
        Get signpost suggestions for building connections.

        Args:
            domain: Optional domain for domain-specific suggestions

        Returns:
            Dict with general signposts and optional domain-specific ones
        """
        general = self.loader.get_general_signposts()
        result = {
            "general_signposts": general,
            "reflection_prompt": self.loader.get_signpost_reflection_prompt(),
            "encouragement": self.loader.get_signpost_encouragement(),
        }

        if domain and domain not in ["logistics", "crisis", "harmful"]:
            domain_signposts = self.loader.get_domain_signposts(domain)
            if domain_signposts:
                result["domain_signposts"] = domain_signposts
                result["domain"] = domain

        return result

    def get_first_contact_templates(self, situation: str = None) -> Dict:
        """
        Get first-contact templates for initiating new connections.

        Args:
            situation: Specific situation (e.g., 'at_a_group_or_meetup')
                      If None, returns all situations

        Returns:
            Dict with templates and guidance
        """
        if situation:
            return self.loader.get_first_contact_situation(situation)

        return {
            "situations": self.loader.get_all_first_contact_situations(),
            "principles": self.loader.get_first_contact_principles(),
            "affirmation": self.loader.get_first_contact_affirmation(),
        }

    def get_building_network_content(self, domain: str = None) -> Dict:
        """
        Get all content for the "Building Your Network" mode.

        This is shown when the user's trusted network is empty,
        shifting the framing from "reach out to someone" to
        "let's think about where you might find your people."

        Args:
            domain: Optional current conversation domain

        Returns:
            Dict with signposts, first-contact templates, and prompts
        """
        return {
            "signposts": self.get_signposts(domain),
            "first_contact": self.get_first_contact_templates(),
            "setup_prompt": self.get_setup_prompt(),
            "is_empty": self.is_network_empty(),
        }

    # ==================== HEALTH METRICS ====================

    def get_connection_health(self) -> Dict:
        """
        Get metrics about connection health.

        Success = more reach outs, less AI usage.
        """
        people = self.get_all_people()
        reach_outs_week = self.count_reach_outs_this_week()
        reach_outs_month = len(self.get_recent_reach_outs(30))
        neglected = self.get_neglected_contacts()

        return {
            "total_trusted_people": len(people),
            "reach_outs_this_week": reach_outs_week,
            "reach_outs_this_month": reach_outs_month,
            "neglected_contacts": len(neglected),
            "network_configured": len(people) > 0,
            "is_reaching_out": reach_outs_week > 0,
        }

    def clear_data(self):
        """Clear all network data."""
        # Use storage backend if SQLite is enabled
        if self._backend is not None and settings.USE_SQLITE:
            self._backend.clear_all_data()
            return

        # JSON backend
        self._save_data({"people": [], "reach_outs": [], "created_at": datetime.now().isoformat()})

    # ==================== CONTEXT-AWARE HANDOFF (PHASE 5) ====================

    def get_contextual_handoff(
        self,
        emotional_weight: str = None,
        session_intent: str = None,
        domain: str = None,
        dependency_score: float = 0,
        is_late_night: bool = False,
        sessions_today: int = 0,
    ) -> Dict:
        """
        Get context-aware handoff template based on session state.

        Args:
            emotional_weight: 'high_weight', 'medium_weight', or 'low_weight'
            session_intent: 'practical', 'processing', 'emotional', 'connection'
            domain: Current conversation domain
            dependency_score: User's dependency score (0-10)
            is_late_night: Whether it's a late night session
            sessions_today: Number of sessions today

        Returns:
            Dict with context, intro_prompt, and message template
        """
        # Detect context
        context = self.loader.detect_handoff_context(
            emotional_weight=emotional_weight,
            session_intent=session_intent,
            domain=domain,
            dependency_score=dependency_score,
            is_late_night=is_late_night,
            sessions_today=sessions_today,
        )

        # Get intro prompt
        intro_prompts = self.loader.get_handoff_intro_prompts(context)
        intro_prompt = random.choice(intro_prompts) if intro_prompts else None

        # Get message templates (domain-aware for after_sensitive_topic)
        messages = self.loader.get_handoff_messages(context, domain)
        message = random.choice(messages) if messages else None

        # Get follow-up prompts
        follow_up_prompts = self.loader.get_handoff_follow_up_prompts(context)
        follow_up = random.choice(follow_up_prompts) if follow_up_prompts else None

        return {
            "context": context,
            "intro_prompt": intro_prompt,
            "message_template": message,
            "follow_up_prompt": follow_up,
            "domain": domain,
        }

    def log_handoff_initiated(
        self, context: str, domain: str = None, person_name: str = None, message_sent: str = None
    ) -> Dict:
        """
        Log when user initiates a handoff.

        Args:
            context: The handoff context (e.g., 'after_difficult_task')
            domain: Current conversation domain
            person_name: Name of person being reached out to
            message_sent: The message user is sending

        Returns:
            The handoff record
        """
        data = self._load_data()

        if "handoffs" not in data:
            data["handoffs"] = []

        handoff = {
            "id": len(data["handoffs"]) + 1,
            "datetime": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "context": context,
            "domain": domain,
            "person_name": person_name,
            "message_preview": message_sent[:100] if message_sent else None,
            "status": "initiated",  # initiated, reached_out, follow_up_pending, completed
            "outcome": None,  # very_helpful, somewhat_helpful, not_helpful
            "follow_up_shown": False,
        }

        data["handoffs"].append(handoff)
        self._save_data(data)

        return handoff

    def record_handoff_outcome(
        self, handoff_id: int, reached_out: bool, outcome: str = None
    ) -> Optional[Dict]:
        """
        Record the outcome of a handoff.

        Args:
            handoff_id: ID of the handoff record
            reached_out: Whether user actually reached out
            outcome: 'very_helpful', 'somewhat_helpful', 'not_helpful', or None

        Returns:
            Updated handoff record
        """
        data = self._load_data()
        handoffs = data.get("handoffs", [])

        for handoff in handoffs:
            if handoff.get("id") == handoff_id:
                if reached_out:
                    handoff["status"] = "completed"
                    handoff["outcome"] = outcome
                    handoff["reached_out"] = True
                    handoff["outcome_date"] = datetime.now().isoformat()

                    # Also log as a reach_out for connection health
                    self.log_reach_out(
                        handoff.get("person_name", "someone"),
                        method="message",
                        topic=handoff.get("domain", "general"),
                        notes=f"Context: {handoff.get('context')}",
                    )
                else:
                    handoff["status"] = "completed"
                    handoff["reached_out"] = False
                    handoff["outcome"] = outcome

                self._save_data(data)
                return handoff

        return None

    def get_pending_follow_ups(self) -> List[Dict]:
        """
        Get handoffs that need follow-up.

        Returns:
            List of handoff records needing follow-up
        """
        data = self._load_data()
        handoffs = data.get("handoffs", [])
        settings = self.loader.get_handoff_settings()

        delay_hours = settings.get("follow_up_delay_hours", 24)
        max_per_week = settings.get("max_follow_ups_per_week", 2)

        # Count follow-ups shown this week
        week_ago = (datetime.now() - __import__("datetime").timedelta(days=7)).isoformat()
        follow_ups_this_week = sum(
            1 for h in handoffs if h.get("follow_up_shown") and h.get("datetime", "") >= week_ago
        )

        if follow_ups_this_week >= max_per_week:
            return []

        # Find handoffs needing follow-up
        pending = []
        cutoff = (datetime.now() - __import__("datetime").timedelta(hours=delay_hours)).isoformat()

        for handoff in handoffs:
            if (
                handoff.get("status") == "initiated"
                and not handoff.get("follow_up_shown")
                and handoff.get("datetime", "") < cutoff
            ):
                pending.append(handoff)

        return pending

    def mark_follow_up_shown(self, handoff_id: int) -> None:
        """Mark a handoff's follow-up as shown."""
        data = self._load_data()
        handoffs = data.get("handoffs", [])

        for handoff in handoffs:
            if handoff.get("id") == handoff_id:
                handoff["follow_up_shown"] = True
                handoff["follow_up_shown_date"] = datetime.now().isoformat()
                self._save_data(data)
                return

    def get_handoff_stats(self, days: int = 30) -> Dict:
        """
        Get handoff statistics for success metrics.

        Returns:
            Dict with handoff stats
        """
        data = self._load_data()
        handoffs = data.get("handoffs", [])

        cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).isoformat()
        recent = [h for h in handoffs if h.get("datetime", "") >= cutoff]

        # Count outcomes
        initiated = len(recent)
        reached_out = sum(1 for h in recent if h.get("reached_out"))
        very_helpful = sum(1 for h in recent if h.get("outcome") == "very_helpful")
        somewhat_helpful = sum(1 for h in recent if h.get("outcome") == "somewhat_helpful")
        not_helpful = sum(1 for h in recent if h.get("outcome") == "not_helpful")

        # Count by context
        by_context = {}
        for h in recent:
            ctx = h.get("context", "general")
            by_context[ctx] = by_context.get(ctx, 0) + 1

        return {
            "total_initiated": initiated,
            "total_reached_out": reached_out,
            "reach_out_rate": reached_out / initiated if initiated > 0 else 0,
            "outcomes": {
                "very_helpful": very_helpful,
                "somewhat_helpful": somewhat_helpful,
                "not_helpful": not_helpful,
            },
            "by_context": by_context,
            "days_analyzed": days,
        }

    def get_handoff_celebration(self, outcome: str = "reached_out") -> str:
        """Get celebration message for handoff outcome."""
        celebrations = self.loader.get_handoff_celebrations(outcome)
        if celebrations:
            return random.choice(celebrations)

        # Fallback
        if outcome == "reached_out":
            return "You reached out. That's what matters."
        return "Good. Keep building those human connections."
