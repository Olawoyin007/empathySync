"""Sidebar rendering for empathySync. Brand header, navigation, tools, and data management."""

import json
from datetime import datetime, date

import streamlit as st

from config.settings import settings
from utils.transcript import generate_markdown_transcript
from ui.panels import (
    display_usage_health,
    display_my_patterns_dashboard,
    display_reality_check,
    display_independence_button,
    display_independence_form,
)
from ui.network import (
    display_trusted_network_setup,
    display_building_your_network,
    display_bring_someone_in,
)
from ui.lock import is_read_only


def save_session_on_end():
    """Save session data when ending conversation."""
    guide = st.session_state.wellness_guide
    tracker = st.session_state.wellness_tracker

    if hasattr(st.session_state, "session_start"):
        duration = (datetime.now() - st.session_state.session_start).total_seconds() / 60
        session_summary = guide.get_session_summary()

        tracker.add_session(
            duration_minutes=int(duration),
            turn_count=session_summary["turn_count"],
            domains_touched=session_summary["domains_touched"],
            max_risk_weight=session_summary["max_risk_weight"],
        )


def render_sidebar(logo_b64: str):
    with st.sidebar:
        wellness_mode = "Balanced"

        # Brand at top of sidebar
        _logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" ' f'alt="logo" class="es-brand-logo">'
            if logo_b64
            else ""
        )
        st.markdown(
            f"""
            <div class="es-brand">
                {_logo_html}
                <span class="es-brand-name">empathy<span>Sync</span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # Read-only mode indicator (Phase 11)
        if is_read_only():
            st.error("**Writes blocked** - another device has the lock")

        # New Chat - the primary action, always visible
        if st.button("New Chat", icon=":material/add:", use_container_width=True, type="primary"):
            save_session_on_end()
            session = st.session_state.conversation_session
            session.reset()
            st.session_state.messages = session.messages
            st.session_state.session_start = datetime.now()
            st.session_state.show_reality_check = False
            st.session_state.show_network_setup = False
            st.session_state.show_my_patterns = False
            st.session_state.show_transparency = False
            tracker = st.session_state.wellness_tracker
            st.session_state.show_intent_check_in = tracker.should_show_intent_check_in()
            st.session_state.show_connection_redirect = False
            st.session_state.show_skill_tips = None
            st.session_state.show_independence_form = False
            st.session_state.show_handoff_follow_up = False
            st.session_state.show_handoff_outcome = False
            st.session_state.pending_handoff_for_outcome = None
            st.session_state.pending_handoff_info = None
            st.session_state.show_session_summary = False
            st.rerun()

        # Subtle usage stats + model badge on same line
        display_usage_health()
        if settings.OLLAMA_MODEL:
            st.markdown(
                f'<span class="es-model-badge">{settings.OLLAMA_MODEL}</span>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # === TOOLS - compact icon + label buttons ===
        reality_active = st.session_state.get("show_reality_check", False)
        network_active = st.session_state.get("show_network_setup", False)
        patterns_active = st.session_state.get("show_my_patterns", False)

        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "People",
                icon=":material/group:",
                use_container_width=True,
                type="primary" if network_active else "secondary",
            ):
                if network_active:
                    st.session_state.show_network_setup = False
                else:
                    st.session_state.show_network_setup = True
                    st.session_state.show_reality_check = False
                    st.session_state.show_my_patterns = False
                st.rerun()
        with col2:
            if st.button(
                "Patterns",
                icon=":material/insights:",
                use_container_width=True,
                type="primary" if patterns_active else "secondary",
            ):
                if patterns_active:
                    st.session_state.show_my_patterns = False
                else:
                    st.session_state.show_my_patterns = True
                    st.session_state.show_reality_check = False
                    st.session_state.show_network_setup = False
                st.rerun()

        # Show the active panel (only one at a time)
        if st.session_state.get("show_my_patterns"):
            st.markdown("---")
            display_my_patterns_dashboard()
        elif st.session_state.get("show_network_setup"):
            st.markdown("---")
            network = st.session_state.trusted_network
            if network.is_network_empty():
                guide = st.session_state.wellness_guide
                current_domain = None
                if guide.last_risk_assessment:
                    current_domain = guide.last_risk_assessment.get("domain")
                display_building_your_network(domain=current_domain)
            else:
                display_trusted_network_setup()
            if st.button("Done", use_container_width=True):
                st.session_state.show_network_setup = False
                st.rerun()
        elif st.session_state.get("show_reality_check"):
            display_reality_check()

        # === SECONDARY ACTIONS - compact row ===
        if not reality_active:
            if st.button(
                "Reality Check",
                icon=":material/pace:",
                use_container_width=True,
            ):
                st.session_state.show_reality_check = True
                st.session_state.show_network_setup = False
                st.session_state.show_my_patterns = False
                st.rerun()

        # Transparency toggle
        guide = st.session_state.wellness_guide
        if guide.last_risk_assessment and st.session_state.messages:
            transparency_active = st.session_state.get("show_transparency", False)
            label = "Hide details" if transparency_active else "Why this response?"
            if st.button(label, icon=":material/visibility:", use_container_width=True):
                st.session_state.show_transparency = not transparency_active
                st.rerun()

        # Reach out
        current_domain = "general"
        if guide.last_risk_assessment:
            current_domain = guide.last_risk_assessment.get("domain", "general")
        if current_domain in ["relationships", "money", "health", "spirituality", "emotional"]:
            with st.expander("Reach Out", expanded=False):
                display_bring_someone_in(current_domain)

        # Independence button
        if not any([reality_active, network_active, patterns_active]):
            if st.session_state.get("show_independence_form"):
                display_independence_form()
            else:
                display_independence_button()

        st.markdown("---")

        # === SESSION & DATA - compact ===
        with st.expander("Session & Data", expanded=False):
            if guide.session_turn_count > 0:
                if st.button(
                    "View Session Summary",
                    use_container_width=True,
                ):
                    st.session_state.show_session_summary = True
                    st.rerun()

            tracker = st.session_state.wellness_tracker
            data = tracker._load_data()
            st.download_button(
                "Export Data",
                data=json.dumps(data, indent=2),
                file_name=f"empathysync_{date.today()}.json",
                mime="application/json",
                use_container_width=True,
            )

            messages = st.session_state.get("messages", [])
            if messages:
                transcript_md = generate_markdown_transcript(
                    messages=messages,
                    exported_at=datetime.now(),
                    session_turns=len([m for m in messages if m.get("role") == "user"]),
                    domains=list(st.session_state.get("session_domains", [])),
                    app_version=settings.APP_VERSION,
                )
                st.download_button(
                    "Export Transcript",
                    data=transcript_md,
                    file_name=f"empathysync_transcript_{date.today()}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            st.caption("All data stays on your device.")

            if "confirm_reset" not in st.session_state:
                st.session_state.confirm_reset = False

            if st.session_state.confirm_reset:
                st.warning("This will delete all data. Cannot be undone.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, reset", use_container_width=True, type="primary"):
                        tracker.reset_all_data()
                        st.session_state.confirm_reset = False
                        st.success("Data cleared.")
                        st.rerun()
                with col_no:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state.confirm_reset = False
                        st.rerun()
            else:
                if st.button("Reset All Data", use_container_width=True):
                    st.session_state.confirm_reset = True
                    st.rerun()

    return wellness_mode
