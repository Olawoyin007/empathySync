"""
The write boundary for caller-supplied field names (issue #236).

Four places merge a dict a caller handed them straight into a record that is
about to be written to disk: `TrustedNetwork.update_person` and the three
`JSONBackend.update_*` methods. SQLite refuses an unknown name through the
column whitelist behind the no-SQL-injection control. The JSON side did not, so
`{"conversation_text": ...}` or `{"persona_summary": ...}` persisted - the two
categories the restraint-memory invariant exists to forbid.

Nothing in `src/` passed arbitrary keys, so nothing was being stored wrongly.
The guarantee simply rested on every caller choosing well rather than on the
boundary enforcing anything, which is the kind of promise that holds until
somebody writes a new caller.

The allowlist here is the same `restraint_memory.allowed_fields` that
`tests/test_restraint_memory.py` asserts against, so the code enforces the list
the invariant is written in terms of rather than a second copy that can drift
from it.
"""

from functools import lru_cache
from pathlib import Path
from typing import Dict

import yaml

ALLOWLIST_PATH = Path(__file__).parent.parent.parent / "scenarios/config/system_defaults.yaml"


@lru_cache(maxsize=1)
def _allowed_fields() -> Dict[str, frozenset]:
    config = yaml.safe_load(open(ALLOWLIST_PATH))["restraint_memory"]["allowed_fields"]
    return {record: frozenset(fields) for record, fields in config.items()}


def validate_persisted_fields(record: str, updates: Dict) -> Dict:
    """
    Return `updates` unchanged, or raise ValueError naming the offending keys.

    `record` is a key of restraint_memory.allowed_fields - "people",
    "task_patterns", "handoff_events" and so on. An unknown record name raises
    too: a new container that nobody added to the allowlist is exactly the
    reviewed decision the invariant is meant to force.
    """
    allowed = _allowed_fields().get(record)
    if allowed is None:
        raise ValueError(
            f"No persisted-field allowlist for record '{record}'. Add it to "
            "restraint_memory.allowed_fields - persisting a new record type is a "
            "conscious, reviewed decision."
        )
    unexpected = set(updates) - allowed
    if unexpected:
        raise ValueError(
            f"Field(s) not persistable for {record}: {sorted(unexpected)}. "
            f"Allowed: {sorted(allowed)}. Conversation content and "
            "preference/persona data are never persistable (restraint_memory invariant)."
        )
    return updates
