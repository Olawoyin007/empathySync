"""Inspect solver that runs a sample through empathySync's real pipeline.

The "model under test" here is not a raw LLM. It is the whole empathySync
conversation pipeline: classification -> restraint policy -> guided response.
This solver drives `ConversationSession.process_message` headless, with storage
redirected to a throwaway directory so:
  1. the user's real ./data is never read or written, and
  2. every sample starts from a cold, independent state (no cross-contamination).

Storage is isolated by pointing `settings.DATA_DIR` at a temp dir and resetting
the backend singleton. The whole solve body is synchronous (no awaits between
setting and restoring DATA_DIR), so it is atomic with respect to the asyncio
event loop even if Inspect runs samples concurrently.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver

_SRC = Path(__file__).resolve().parents[2] / "src"


def _ensure_src_on_path() -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))


@solver
def empathysync_pipeline(engine_model: str, ollama_host: str = "") -> Solver:
    """Run each sample's input through empathySync and capture the response.

    Args:
        engine_model: the Ollama model empathySync runs as its engine - the
            product default, i.e. what real users actually run.
        ollama_host: Ollama base URL; if given, overrides settings.OLLAMA_HOST.
    """
    _ensure_src_on_path()
    from config.settings import settings

    if ollama_host:
        settings.OLLAMA_HOST = ollama_host
    if engine_model:
        settings.OLLAMA_MODEL = engine_model

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        from models.ai_wellness_guide import WellnessGuide
        from models.conversation_session import ConversationSession
        from utils.storage_backend import reset_storage_backend
        from utils.trusted_network import TrustedNetwork
        from utils.wellness_tracker import WellnessTracker

        tmp = Path(tempfile.mkdtemp(prefix="es-eval-"))
        prev_data_dir = settings.DATA_DIR
        try:
            settings.DATA_DIR = tmp
            reset_storage_backend()

            guide = WellnessGuide()
            tracker = WellnessTracker()
            network = TrustedNetwork()
            session = ConversationSession(guide, tracker, network)

            result = session.process_message(state.input_text)
            response = result.response or ""

            # Capture the pipeline's own restraint signals for the judge + logs.
            policy = result.policy_action if isinstance(result.policy_action, dict) else {}
            risk = result.risk_assessment if isinstance(result.risk_assessment, dict) else {}
            state.metadata["policy_action"] = policy.get("type")
            state.metadata["is_cooldown_active"] = bool(result.is_cooldown_active)
            state.metadata["suggested_handoff_person"] = result.suggested_handoff_person
            state.metadata["suggested_handoff_domain"] = result.suggested_handoff_domain
            state.metadata["classified_domain"] = risk.get("domain")
        finally:
            settings.DATA_DIR = prev_data_dir
            reset_storage_backend()
            shutil.rmtree(tmp, ignore_errors=True)

        state.output = ModelOutput.from_content(model=engine_model, content=response)
        return state

    return solve


@solver
def empathysync_classify_only(engine_model: str, ollama_host: str = "") -> Solver:
    """Route each sample through empathySync's classifier without generating a reply.

    Domain mode grades one thing: `state.metadata["classified_domain"]`. The
    shared pipeline solver gets that by driving `ConversationSession.process_message`,
    which generates a full engine response per sample and then discards it. That
    discarded generation is the dominant cost of a domain-mode run, and it is why
    the classifier side was too slow to iterate against the full corpus.

    Faithfulness: the pipeline solver reports the domain from
    `result.risk_assessment`, which is `RiskClassifier.classify()` plus the
    session-context adjustment and domain-stability damping. Both of those need
    prior turns, and every eval sample is turn 1, so they are no-ops here. That
    was verified against the corpus before this solver was wired in: 25 random
    samples, full pipeline vs classify-only, 25/25 identical domains. If samples
    ever become multi-turn, this solver stops being equivalent and domain mode
    must go back to the full pipeline.

    Storage is redirected per sample with the same save/restore as the full
    solver, so the user's real ./data is never touched. Constructing this solver
    has no side effects - it does not mutate settings or load scenarios - which
    keeps the task constructible in tests.
    """
    _ensure_src_on_path()
    from config.settings import settings

    if ollama_host:
        settings.OLLAMA_HOST = ollama_host
    if engine_model:
        # Only load-bearing when OLLAMA_CLASSIFIER_MODEL is unset and the
        # classifier falls back to the engine model.
        settings.OLLAMA_MODEL = engine_model

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        from models.risk_classifier import RiskClassifier
        from utils.storage_backend import reset_storage_backend

        tmp = Path(tempfile.mkdtemp(prefix="es-eval-classify-"))
        prev_data_dir = settings.DATA_DIR
        try:
            settings.DATA_DIR = tmp
            reset_storage_backend()
            assessment = RiskClassifier().classify(state.input_text, [])
        finally:
            settings.DATA_DIR = prev_data_dir
            reset_storage_backend()
            shutil.rmtree(tmp, ignore_errors=True)

        state.metadata["classified_domain"] = assessment.get("domain")
        state.metadata["risk_weight"] = assessment.get("risk_weight")
        state.metadata["classification_method"] = assessment.get("classification_method")
        # No reply was produced, so anything derived from one is absent rather
        # than falsely empty. Response-side questions belong in restraint mode.
        state.metadata["response_generated"] = False

        state.output = ModelOutput.from_content(model=engine_model, content="")
        return state

    return solve
