"""
Chat interface for empathySync.
Message display, input handling, and streaming responses.
"""

import random

import streamlit as st

from ui.lock import is_read_only
from ui.panels import (
    display_transparency_panel,
    display_skill_tips,
    display_intent_shift_prompt,
    display_graduation_prompt,
)

ASSISTANT_AVATAR = "assets/avatar_assistant.png"
USER_AVATAR = "assets/avatar_user.png"


def display_chat_interface(wellness_mode):
    """Display the main chat interface.

    Uses ConversationSession (Phase 16) for all conversation orchestration.
    This function handles only rendering and user interaction.
    """
    session = st.session_state.conversation_session
    guide = session.guide
    tracker = session.tracker
    network = session.network

    # Check for cooldown
    people = network.get_all_people()
    should_cooldown, cooldown_reason = tracker.should_enforce_cooldown()
    if should_cooldown:
        st.warning(cooldown_reason)

        if people:
            person = random.choice(people)
            st.markdown(f"**Consider calling {person['name']}** instead of being here.")
        else:
            st.markdown("**Consider:** Who could you call right now?")

        for message in session.messages:
            with st.chat_message(
                message["role"],
                avatar=ASSISTANT_AVATAR if message["role"] == "assistant" else USER_AVATAR,
            ):
                st.markdown(message["content"])
        return

    # Display existing messages
    for message in session.messages:
        with st.chat_message(
            message["role"],
            avatar=ASSISTANT_AVATAR if message["role"] == "assistant" else USER_AVATAR,
        ):
            st.markdown(message["content"])

    # Welcome screen when no messages yet
    if not session.messages:
        st.markdown(
            """
            <div class="es-welcome">
                <h2>What are you thinking through?</h2>
                <p>I can help you work through tasks, think through decisions,
                or sort out something on your mind.</p>
                <div class="es-welcome-hint">
                    This is a tool, not a friend - real people are better for real connection
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # === ONE panel at a time in main area (priority order) ===
    panel_shown = False

    # Phase 6: Show transparency panel if we have assessment data
    if (
        guide.last_risk_assessment
        and session.messages
        and session.messages[-1]["role"] == "assistant"
    ):
        display_transparency_panel()
        panel_shown = True

    # Priority 2: Skill tips (user requested)
    if not panel_shown and st.session_state.get("show_skill_tips"):
        display_skill_tips(st.session_state.show_skill_tips)
        panel_shown = True

    # Priority 3: Intent shift prompt
    if not panel_shown and session.pending_shift and not session.acknowledged_shift:
        display_intent_shift_prompt(session.pending_shift)
        panel_shown = True

    # Priority 4: Graduation prompt
    if (
        not panel_shown
        and session.pending_graduation
        and not st.session_state.get("show_skill_tips")
    ):
        grad = session.pending_graduation
        display_graduation_prompt(grad["category"], grad["prompt"])
        session.pending_graduation = None
        session.graduation_shown_this_session = True

    # Chat input (disabled in read-only mode)
    if is_read_only():
        st.chat_input("Read-only mode: close empathySync on other device first", disabled=True)
    elif prompt := st.chat_input("Type here..."):
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        # st.spinner() is the only mechanism that flushes to the browser
        # before a blocking call - it sends an immediate WebSocket message
        # to the frontend rather than queuing a delta like st.empty() does.
        with st.spinner(""):
            result = session.process_message_stream(prompt)

        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            if result.is_streaming:
                st.write_stream(result.response_stream)
                result = session.finalize_stream()
            else:
                st.markdown(result.response)

        # Sync messages reference for backward compatibility
        st.session_state.messages = session.messages

        if result.should_rerun:
            st.rerun()
