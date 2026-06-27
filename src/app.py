"""
empathySync - Help that knows when to stop
Main Streamlit application entry point

Core principle: Optimize for exit, not engagement.
Bridge people back to human connection.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.append(str(Path(__file__).parent))

from config.settings import settings
from models.ai_wellness_guide import WellnessGuide
from utils.helpers import setup_logging, validate_environment
from utils.wellness_tracker import WellnessTracker
from utils.trusted_network import TrustedNetwork
from utils.health_check import run_health_checks, has_critical_failures, auto_pull_model

# UI modules (Phase 16.12)
from ui.styles import LOGO_B64, apply_page_config, apply_custom_css
from ui.lock import display_lock_warning, display_lock_banner, is_read_only
from ui.chat import display_chat_interface
from ui.sidebar import render_sidebar
from ui.panels import display_connection_redirect, display_session_summary
from ui.network import (
    display_building_your_network,
    display_handoff_follow_up,
    display_handoff_outcome,
)

# Configure page (must be first Streamlit call)
apply_page_config()

# Apply custom CSS
apply_custom_css()


def display_encryption_notice():
    """One-time notice that local data is stored unencrypted.

    THREAT_MODEL.md is explicit that there is no encryption at rest, but a user
    running on a shared machine will not read it before their conversation
    history is written to disk. This surfaces that honesty in the UI itself,
    matching the transparency philosophy used elsewhere. Only shown when
    persistence is on; dismissing it writes a marker so it never nags again.
    """
    if not settings.STORE_CONVERSATIONS:
        return
    ack_marker = settings.DATA_DIR / ".encryption_notice_ack"
    if ack_marker.exists():
        return
    st.caption(
        f"Conversations are stored **unencrypted** at `{settings.DATA_DIR}`. "
        "On a shared machine, enable full-disk encryption. See `THREAT_MODEL.md`."
    )
    if st.button("Understood - don't show this again"):
        try:
            ack_marker.touch()
        except OSError:
            pass  # Non-critical: the notice simply shows again next launch
        st.rerun()


def main():
    """Main application function"""

    setup_logging()

    missing_config = validate_environment()
    if missing_config:
        st.error("Configuration Required")
        st.markdown("Please configure these environment variables in your `.env` file:")
        for config in missing_config:
            st.code(f"{config}=your_value_here")
        st.markdown("See `.env.example` for guidance.")
        return

    # Phase 13: Startup health checks (run once per session)
    if "health_checks_passed" not in st.session_state:
        checks = run_health_checks()
        if has_critical_failures(checks):
            # Check if the only critical failure is "no models" - try auto-pull
            model_check = next((c for c in checks if c.name == "Ollama Model"), None)
            server_ok = any(c.name == "Ollama Server" and c.ok for c in checks)
            if (
                model_check
                and not model_check.ok
                and server_ok
                and "No models installed" in model_check.message
            ):
                model_to_pull = settings.OLLAMA_MODEL or "llama3.2"
                with st.spinner(
                    f"No models found. Pulling `{model_to_pull}`... this may take a few minutes"
                ):
                    if auto_pull_model(model_to_pull):
                        settings.OLLAMA_MODEL = model_to_pull
                        st.success(f"Model `{model_to_pull}` downloaded successfully!")
                        st.session_state.health_checks_passed = True
                        st.rerun()
                    else:
                        st.error(
                            f"Failed to pull `{model_to_pull}`. Please run manually: `ollama pull {model_to_pull}`"
                        )
                        return

            st.error("**Startup Check Failed**")
            for check in checks:
                if check.ok:
                    st.success(f"**{check.name}**: {check.message}")
                elif check.critical:
                    st.error(f"**{check.name}**: {check.message}")
                    if check.details:
                        st.markdown(check.details)
                else:
                    st.warning(f"**{check.name}**: {check.message}")
                    if check.details:
                        st.markdown(check.details)
            st.markdown("---")
            st.markdown("Fix the issues above and refresh the page.")
            return
        # Show non-critical warnings (e.g., model fallback) without blocking
        for check in checks:
            if check.ok and check.details:
                st.info(f"**{check.name}**: {check.message}")
                st.caption(check.details)
        st.session_state.health_checks_passed = True

    # Data pruning: remove records older than DATA_RETENTION_DAYS (runs once per session)
    if "data_pruned" not in st.session_state:
        if settings.DATA_RETENTION_DAYS > 0:
            try:
                from utils.storage_backend import get_storage_backend

                backend = get_storage_backend()
                backend.prune_old_data(settings.DATA_RETENTION_DAYS)
            except Exception:
                pass  # Non-critical: pruning can retry next session
        st.session_state.data_pruned = True

    # One-time notice: local data is stored unencrypted at rest (THREAT_MODEL.md)
    display_encryption_notice()

    # Phase 11: Check device lock status (enables read-only mode if locked by other)
    display_lock_warning()

    # Initialize session state
    if "wellness_guide" not in st.session_state:
        st.session_state.wellness_guide = WellnessGuide()
    if "wellness_tracker" not in st.session_state:
        st.session_state.wellness_tracker = WellnessTracker()
    if "trusted_network" not in st.session_state:
        st.session_state.trusted_network = TrustedNetwork()
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now()
    # Phase 16: ConversationSession owns messages and conversation state
    if "conversation_session" not in st.session_state:
        from models.conversation_session import ConversationSession

        st.session_state.conversation_session = ConversationSession(
            guide=st.session_state.wellness_guide,
            tracker=st.session_state.wellness_tracker,
            network=st.session_state.trusted_network,
        )
    # Backward-compatible alias: st.session_state.messages points to session.messages
    if "messages" not in st.session_state:
        st.session_state.messages = st.session_state.conversation_session.messages
    # UI toggle state (stays in st.session_state - not conversation logic)
    if "show_reality_check" not in st.session_state:
        st.session_state.show_reality_check = False
    if "show_network_setup" not in st.session_state:
        st.session_state.show_network_setup = False
    if "show_intent_check_in" not in st.session_state:
        tracker = st.session_state.wellness_tracker
        st.session_state.show_intent_check_in = tracker.should_show_intent_check_in()
    if "show_connection_redirect" not in st.session_state:
        st.session_state.show_connection_redirect = False
    if "show_skill_tips" not in st.session_state:
        st.session_state.show_skill_tips = None
    if "show_independence_form" not in st.session_state:
        st.session_state.show_independence_form = False
    # Phase 5: Handoff UI state
    if "show_handoff_follow_up" not in st.session_state:
        st.session_state.show_handoff_follow_up = False
    if "show_handoff_outcome" not in st.session_state:
        st.session_state.show_handoff_outcome = False
    if "pending_handoff_for_outcome" not in st.session_state:
        st.session_state.pending_handoff_for_outcome = None
    if "pending_handoff_info" not in st.session_state:
        st.session_state.pending_handoff_info = None
    # Phase 6: Transparency tracking
    if "show_session_summary" not in st.session_state:
        st.session_state.show_session_summary = False
    # Phase 7: Success metrics
    if "show_my_patterns" not in st.session_state:
        st.session_state.show_my_patterns = False
    # Phase 6: Transparency panel opt-in
    if "show_transparency" not in st.session_state:
        st.session_state.show_transparency = False

    # Phase 11: Show lock banner if in read-only mode
    if is_read_only() and not st.session_state.get("lock_banner_dismissed"):
        display_lock_banner()

    # Phase 4: Show connection redirect if user indicated they just want to talk
    if st.session_state.get("show_connection_redirect"):
        display_connection_redirect()
        return

    # Phase 5: Check for pending handoff follow-ups
    if not st.session_state.get("show_handoff_follow_up") and not st.session_state.get(
        "show_handoff_outcome"
    ):
        tracker = st.session_state.wellness_tracker
        should_show, pending = tracker.should_show_handoff_follow_up()
        if should_show and pending:
            st.session_state.show_handoff_follow_up = True
            st.session_state.pending_handoff_info = pending

    # Phase 5: Show handoff follow-up if pending
    if st.session_state.get("show_handoff_outcome"):
        display_handoff_outcome()
    elif st.session_state.get("show_handoff_follow_up") and st.session_state.get(
        "pending_handoff_info"
    ):
        display_handoff_follow_up(st.session_state.pending_handoff_info)

    # Phase 6: Show session summary if requested
    if st.session_state.get("show_session_summary"):
        display_session_summary()

    # Check if network is empty - show Building Your Network (Phase 12)
    network = st.session_state.trusted_network
    if (
        not network.get_all_people()
        and not st.session_state.show_network_setup
        and not st.session_state.messages
    ):
        current_domain = None
        if st.session_state.messages:
            guide = st.session_state.wellness_guide
            if hasattr(guide, "_session_state") and guide._session_state.get("domains"):
                current_domain = (
                    guide._session_state["domains"][-1] if guide._session_state["domains"] else None
                )

        with st.expander("No trusted network yet - find your people", expanded=False):
            display_building_your_network(domain=current_domain)

    # Sidebar
    wellness_mode = render_sidebar(LOGO_B64)

    # Main chat interface
    display_chat_interface(wellness_mode)


if __name__ == "__main__":
    main()
