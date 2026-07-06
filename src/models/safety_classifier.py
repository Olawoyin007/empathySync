"""
LlamaGuard safety classifier (Phase 21.2) - ADDITIVE input-side safety layer.

Runs a dedicated guard model (llama-guard3:1b, chosen in Phase 21.1) alongside
the existing prompt-engineered RiskClassifier. It is NOT a replacement: the guard
catches dangerous requests the base classifier can miss, but it is blind to
fiction / hypothetical framing that the base classifier handles - so both run.

Design constraints, straight from the Phase 21.1 evaluation:

  - Category-mapped, never a blanket block. LlamaGuard reports MLCommons hazard
    categories S1-S14. The single most important mapping: S6 (specialized
    medical / financial / legal advice) is an empathySync RESTRAINT domain, not a
    refusal - every guard false positive in the eval was a health or money
    question. Treating "unsafe" as a blanket block would regress the assistant
    into refusing legitimate health questions.

  - Fail-open. This is defense-in-depth on top of an already-safe pipeline
    (RiskClassifier + mid-stream voice check + post-stream backstop). If the guard
    model is unset or unreachable, classify() returns ALLOW so the base pipeline
    still runs. The guard only ADDS refusals; it is never the sole gate.

  - Off by default. Active only when OLLAMA_SAFETY_MODEL is set.

NOTE (Phase 21.2): this module is landed dark. It is unit-tested but not yet wired
into the request pipeline; mapping SafetyAction into RiskClassifier / the Step 5
hard-stop is a follow-up increment.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class SafetyAction(str, Enum):
    """What empathySync should do with a message, per the guard verdict."""

    ALLOW = "allow"  # no actionable hazard - defer entirely to the base pipeline
    RESTRAIN = "restrain"  # S6 specialized advice - route via existing restraint, do NOT refuse
    CRISIS = "crisis"  # S11 suicide & self-harm - route to crisis intervention
    REFUSE = "refuse"  # dangerous request - map to the 'harmful' hard-stop


# MLCommons hazard taxonomy used by Llama Guard 3 (model-card categories S1-S14),
# mapped to empathySync actions. A category not listed here defaults to REFUSE:
# a flagged hazard with no empathySync-specific handling is refused, the
# conservative direction. The health/money false-positive risk is confined to S6,
# which is handled explicitly below.
_CATEGORY_ACTION = {
    "S1": SafetyAction.REFUSE,  # Violent Crimes
    "S2": SafetyAction.REFUSE,  # Non-Violent Crimes
    "S3": SafetyAction.REFUSE,  # Sex-Related Crimes
    "S4": SafetyAction.REFUSE,  # Child Sexual Exploitation
    "S5": SafetyAction.REFUSE,  # Defamation
    "S6": SafetyAction.RESTRAIN,  # Specialized Advice (medical/financial/legal) - restraint, NOT refuse
    "S7": SafetyAction.REFUSE,  # Privacy
    "S8": SafetyAction.ALLOW,  # Intellectual Property - not an empathySync hazard
    "S9": SafetyAction.REFUSE,  # Indiscriminate Weapons
    "S10": SafetyAction.REFUSE,  # Hate
    "S11": SafetyAction.CRISIS,  # Suicide & Self-Harm - crisis intervention
    "S12": SafetyAction.REFUSE,  # Sexual Content
    "S13": SafetyAction.ALLOW,  # Elections - out of scope for a wellness assistant
    "S14": SafetyAction.ALLOW,  # Code Interpreter Abuse - empathySync runs no code
}

# Highest-priority action wins when a message trips several categories: life-safety
# (crisis) over refusal over restraint over allow.
_ACTION_PRECEDENCE = (
    SafetyAction.CRISIS,
    SafetyAction.REFUSE,
    SafetyAction.RESTRAIN,
    SafetyAction.ALLOW,
)


@dataclass(frozen=True)
class GuardVerdict:
    """Parsed LlamaGuard output: safe flag plus the raw hazard categories."""

    safe: bool
    categories: FrozenSet[str]

    @property
    def action(self) -> SafetyAction:
        if self.safe:
            return SafetyAction.ALLOW
        return action_for_categories(self.categories)


def action_for_categories(categories) -> SafetyAction:
    """Reduce a set of hazard categories to a single SafetyAction by precedence."""
    actions = {_CATEGORY_ACTION.get(c.upper(), SafetyAction.REFUSE) for c in categories}
    for action in _ACTION_PRECEDENCE:
        if action in actions:
            return action
    return SafetyAction.ALLOW


def parse_guard_response(raw: str) -> GuardVerdict:
    """Parse LlamaGuard's text output.

    The model answers with 'safe', or 'unsafe' followed by the violated category
    codes (e.g. 'unsafe\\nS6' or 'unsafe\\nS1,S10'). Anything that is not a clear
    'unsafe' verdict is treated as safe.
    """
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines or lines[0].lower() != "unsafe":
        return GuardVerdict(safe=True, categories=frozenset())

    codes = set()
    for line in lines[1:]:
        for token in line.replace(",", " ").split():
            token = token.upper()
            if token.startswith("S") and token[1:].isdigit():
                codes.add(token)
    return GuardVerdict(safe=False, categories=frozenset(codes))


class SafetyClassifier:
    """Additive LlamaGuard layer over the base classifier. Off unless a model is set.

    Args:
        model: guard model name (default: settings.OLLAMA_SAFETY_MODEL).
        http_client: injectable httpx.Client for testability. If None, the shared
                     module-level client is used.
    """

    def __init__(self, model: Optional[str] = None, http_client: Optional[httpx.Client] = None):
        self.model = model if model is not None else settings.OLLAMA_SAFETY_MODEL
        self._http_client = http_client
        self.chat_url = f"{settings.OLLAMA_HOST}/api/chat"

    @property
    def enabled(self) -> bool:
        """The guard runs only when a model name is configured."""
        return bool(self.model)

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        from utils.http_client import get_http_client

        return get_http_client()

    def classify(self, message: str) -> SafetyAction:
        """Return the SafetyAction for a user message.

        Fail-open: if the guard is disabled or the call fails, returns ALLOW so the
        base pipeline remains authoritative. The guard never becomes the sole gate.
        """
        if not self.enabled:
            return SafetyAction.ALLOW

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
            "stream": False,
            "options": {"temperature": 0.0},
        }
        try:
            response = self.http_client.post(self.chat_url, json=payload, timeout=30)
            response.raise_for_status()
            raw = response.json().get("message", {}).get("content", "")
        except Exception as exc:  # fail-open - an additive layer must never break the pipeline
            logger.warning("safety guard unavailable, failing open (ALLOW): %s", exc)
            return SafetyAction.ALLOW

        return parse_guard_response(raw).action
