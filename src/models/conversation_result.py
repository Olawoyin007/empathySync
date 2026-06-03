"""
ConversationResult - Structured result from processing a message.

Framework-agnostic data class returned by ConversationSession.process_message().
Contains the response and all metadata an interface adapter needs to render it.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional


@dataclass
class ConversationResult:
    """Result of processing a user message through the conversation session."""

    # The assistant's response text
    response: str

    # Risk assessment data (for transparency panel)
    risk_assessment: Optional[Dict] = None

    # Policy action triggered (crisis_stop, harmful_stop, turn_limit, etc.)
    policy_action: Optional[Dict] = None

    # Pending user interactions
    pending_shift: Optional[Dict] = None
    pending_graduation: Optional[Dict] = None
    pending_connection_redirect: Optional[Dict] = None

    # Handoff suggestions from trusted network
    suggested_handoff_person: Optional[str] = None
    suggested_handoff_domain: Optional[str] = None

    # Cooldown state
    is_cooldown_active: bool = False
    cooldown_message: Optional[str] = None

    # Session metadata
    turn_count: int = 0
    should_rerun: bool = False
    steering_active: bool = False

    # Streaming support: when set, response_stream yields tokens progressively
    response_stream: Optional[Iterator[str]] = None

    @property
    def is_streaming(self) -> bool:
        """True if this result contains a token stream instead of a complete response."""
        return self.response_stream is not None
