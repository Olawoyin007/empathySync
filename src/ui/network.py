"""Trusted network UI components for empathySync. Network setup, building connections, handoff, and follow-up."""

import random
from typing import Dict

import streamlit as st

from utils.scenario_loader import get_scenario_loader


def display_trusted_network_setup():
    """Display trusted network setup panel."""
    network = st.session_state.trusted_network

    st.markdown("### Your Trusted People")
    st.markdown("*Who could you call if things got hard?*")

    people = network.get_all_people()

    if people:
        for person in people:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{person['name']}**")
                if person.get("relationship"):
                    st.caption(person["relationship"])
            with col2:
                if st.button("Remove", key=f"remove_{person['id']}", type="secondary"):
                    network.remove_person(person["id"])
                    st.rerun()
    else:
        st.caption("No one added yet.")
        prompt = network.get_setup_prompt()
        st.markdown(f"*{prompt}*")

    st.markdown("---")
    st.markdown("**Add someone:**")

    with st.form("add_person", clear_on_submit=True):
        name = st.text_input("Name", placeholder="e.g., Mom, Jake, Dr. Smith")
        relationship = st.text_input("Relationship", placeholder="e.g., friend, sister, therapist")
        contact = st.text_input(
            "How to reach them", placeholder="e.g., phone, usually free evenings"
        )

        domains = st.multiselect(
            "Good for talking about",
            ["relationships", "money", "health", "spirituality", "general"],
            default=["general"],
        )

        if st.form_submit_button("Add"):
            if name:
                network.add_person(name, relationship, contact, domains=domains)
                st.success(f"Added {name}")
                st.rerun()

    # Phase 12: Always show "Expand Your Network" option
    st.markdown("---")
    with st.expander("Expand Your Network", expanded=False):
        st.markdown("*Looking to find new people to connect with?*")

        # Get current domain if available for context-aware signposts
        guide = st.session_state.wellness_guide
        current_domain = None
        if guide.last_risk_assessment:
            current_domain = guide.last_risk_assessment.get("domain")

        content = network.get_building_network_content(current_domain)
        signposts = content.get("signposts", {})
        first_contact = content.get("first_contact", {})

        # Signposts section
        st.markdown("**Places to find connection:**")
        general = signposts.get("general_signposts", [])
        for signpost in general[:3]:  # Show top 3
            st.markdown(f"- **{signpost.get('category', '')}**")
            st.caption(f"  {signpost.get('search_hint', '')}")

        # Domain-specific signposts if available
        if "domain_signposts" in signposts:
            domain_content = signposts["domain_signposts"]
            st.markdown(f"\n*For {signposts.get('domain', 'your situation')}:*")
            for cat in domain_content.get("categories", [])[:2]:
                st.markdown(f"- {cat.get('category', '')}")

        # First-contact tip
        st.markdown("---")
        st.markdown("**Making first contact:**")
        principles = first_contact.get("principles", [])
        if principles:
            p = principles[0]  # Show just one principle
            st.markdown(f"*{p.get('title', '')}*: {p.get('content', '')}")

        # Encouragement
        encouragement = signposts.get("encouragement", "")
        if encouragement:
            st.info(encouragement)


def display_building_your_network(domain: str = None):
    """
    Display full "Building Your Network" panel (Phase 12).

    Primary use: When trusted network is empty, this replaces the simple "add someone" form.
    Also accessible via "Expand Your Network" expander in regular network setup.

    Shows:
    - Signposts: Types of places to find connection (tabbed view)
    - First-contact templates: How to initiate new connections
    - Add someone form: For when they already have someone in mind
    """
    network = st.session_state.trusted_network

    st.markdown("### Building Your Network")
    st.markdown("*Let's think about where you might find your people.*")

    # Get all content
    content = network.get_building_network_content(domain)
    signposts = content.get("signposts", {})
    first_contact = content.get("first_contact", {})

    # Tabs for different content types
    tab1, tab2, tab3 = st.tabs(["Where to Look", "Making First Contact", "Add Someone"])

    with tab1:
        st.markdown("**Places where people find connection:**")
        st.caption("No specific services-just types of places to search locally.")

        # Show general signposts
        general = signposts.get("general_signposts", [])
        for signpost in general:
            with st.expander(signpost.get("category", ""), expanded=False):
                st.markdown(signpost.get("description", ""))
                st.markdown(f"**Why it works:** {signpost.get('why_it_works', '')}")
                st.caption(signpost.get("search_hint", ""))

        # Show domain-specific signposts if available
        if "domain_signposts" in signposts:
            domain_content = signposts["domain_signposts"]
            st.markdown("---")
            st.markdown(f"**{domain_content.get('intro', '')}**")
            for cat in domain_content.get("categories", []):
                with st.expander(cat.get("category", ""), expanded=False):
                    st.markdown(cat.get("examples", ""))
                    st.caption(cat.get("search_hint", ""))

        # Reflection prompt
        st.markdown("---")
        reflection = signposts.get("reflection_prompt", "")
        if reflection:
            st.markdown(f"*Think about: {reflection}*")

        # Encouragement
        encouragement = signposts.get("encouragement", "")
        if encouragement:
            st.info(encouragement)

    with tab2:
        st.markdown("**Practical tips for initiating connection:**")

        situations = first_contact.get("situations", {})

        # Show each situation as an expander
        situation_titles = {
            "at_a_group_or_meetup": "Starting a conversation at a group",
            "turning_acquaintance_into_friend": "Moving from acquaintance to friend",
            "reconnecting_with_someone_from_the_past": "Reconnecting with someone",
            "joining_a_new_community": "Becoming part of a new community",
            "asking_for_help_or_support": "Asking someone for help",
        }

        for key, title in situation_titles.items():
            if key in situations:
                sit = situations[key]
                with st.expander(title, expanded=False):
                    st.markdown(sit.get("intro", ""))

                    # Show tips if available
                    tips = sit.get("before_tips", []) or sit.get("first_visits", [])
                    if tips:
                        st.markdown("**Tips:**")
                        for tip in tips:
                            st.markdown(f"- {tip}")

                    # Show conversation starters if available
                    starters = sit.get("conversation_starters", [])
                    if starters:
                        st.markdown("**Conversation starters:**")
                        for starter in starters:
                            st.markdown(f"- \"{starter.get('opener', '')}\"")
                            st.caption(f"  *{starter.get('why_it_works', '')}*")

                    # Show templates if available
                    templates = sit.get("templates", []) or sit.get(
                        "ways_to_suggest_hanging_out", []
                    )
                    if templates:
                        st.markdown("**Templates:**")
                        for template in templates:
                            if isinstance(template, dict):
                                st.markdown(f"- \"{template.get('template', '')}\"")
                                if template.get("context"):
                                    st.caption(f"  *{template.get('context', '')}*")
                            else:
                                st.markdown(f'- "{template}"')

        # General principles
        principles = first_contact.get("principles", [])
        if principles:
            st.markdown("---")
            st.markdown("**Remember:**")
            for p in principles[:3]:  # Show just 3
                st.markdown(f"- **{p.get('title', '')}**: {p.get('content', '')}")

        # Affirmation
        affirmation = first_contact.get("affirmation", "")
        if affirmation:
            st.info(affirmation)

    with tab3:
        st.markdown("**Already have someone in mind?**")
        st.caption("Add them here so empathySync can suggest reaching out when it matters.")

        # Reuse the existing add person form
        with st.form("add_person_building", clear_on_submit=True):
            name = st.text_input("Name", placeholder="e.g., Mom, Jake, Dr. Smith")
            relationship = st.text_input(
                "Relationship", placeholder="e.g., friend, sister, therapist"
            )
            contact = st.text_input(
                "How to reach them", placeholder="e.g., phone, usually free evenings"
            )

            domains = st.multiselect(
                "Good for talking about",
                ["relationships", "money", "health", "spirituality", "general"],
                default=["general"],
                key="building_domains",
            )

            if st.form_submit_button("Add"):
                if name:
                    network.add_person(name, relationship, contact, domains=domains)
                    st.success(f"Added {name}!")
                    st.balloons()
                    st.rerun()


def display_bring_someone_in(domain: str = "general"):
    """Enhanced context-aware human handoff panel (Phase 5)."""
    network = st.session_state.trusted_network
    tracker = st.session_state.wellness_tracker
    guide = st.session_state.wellness_guide
    people = network.get_all_people()

    st.markdown("### Bring Someone In")

    # Get session context for smart template selection
    emotional_weight = None
    session_intent = st.session_state.conversation_session.session_intent
    dependency_score = 0

    if guide.last_risk_assessment:
        emotional_weight = guide.last_risk_assessment.get("emotional_weight")
        dependency_score = guide.last_risk_assessment.get("dependency_risk", 0)

    # Get context-aware handoff
    contextual = network.get_contextual_handoff(
        emotional_weight=emotional_weight,
        session_intent=session_intent,
        domain=domain,
        dependency_score=dependency_score,
        is_late_night=tracker.is_late_night_session(),
        sessions_today=tracker.get_wellness_summary().get("sessions_today", 0),
    )

    # Show context-aware intro prompt
    if contextual.get("intro_prompt"):
        st.info(contextual["intro_prompt"])

    # Suggest someone if we have people
    if people:
        suggested = network.suggest_person_for_domain(domain)
        if suggested:
            st.markdown(f"**Consider reaching out to:** {suggested['name']}")
            if suggested.get("relationship"):
                st.caption(suggested["relationship"])
    else:
        prompt = network.get_domain_prompt(domain)
        st.markdown(f"*{prompt}*")

    st.markdown("---")

    # Smart template selection based on context
    context_category = contextual.get("context", "general")

    # Map context to template options
    context_template_map = {
        "after_difficult_task": ["need_to_talk", "asking_for_help", "hard_conversation"],
        "processing_decision": ["need_to_talk", "asking_for_help", "checking_in"],
        "after_sensitive_topic": ["need_to_talk", "hard_conversation", "reconnecting"],
        "high_usage_pattern": ["checking_in", "reconnecting", "need_to_talk"],
        "general": [
            "need_to_talk",
            "reconnecting",
            "checking_in",
            "hard_conversation",
            "asking_for_help",
        ],
    }

    template_options = context_template_map.get(context_category, context_template_map["general"])

    st.markdown("**Need help starting the conversation?**")

    template_type = st.selectbox(
        "What kind of message?",
        template_options,
        format_func=lambda x: {
            "need_to_talk": "I need to talk",
            "reconnecting": "Reconnecting after silence",
            "checking_in": "Just checking in",
            "hard_conversation": "Starting a hard conversation",
            "asking_for_help": "Asking for help",
        }.get(x, x),
        label_visibility="collapsed",
    )

    # Get message template - prefer contextual if available, fallback to standard
    if contextual.get("message_template"):
        base_message = contextual["message_template"]
    else:
        template = network.get_reach_out_template(template_type)
        base_message = template["template"]

    # Build message with context from conversation
    if st.session_state.messages:
        user_msgs = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
        if user_msgs:
            context_snippet = user_msgs[-1][:100]
            full_message = f"{base_message}\n\nI've been thinking about: {context_snippet}..."
        else:
            full_message = base_message
    else:
        full_message = base_message

    message = st.text_area(
        "Message to send:", value=full_message, height=120, label_visibility="collapsed"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Copy message", use_container_width=True):
            st.code(message)
            st.caption("Copy the text above")

    with col2:
        if st.button("I reached out!", use_container_width=True, type="primary"):
            # Log the reach out with context
            person_name = (
                suggested["name"] if people and "suggested" in dir() and suggested else "someone"
            )

            # Log in TrustedNetwork with handoff context
            network.log_handoff_initiated(
                context=context_category,
                domain=domain,
                person_name=person_name,
                message_sent=message,
            )

            # Also log in WellnessTracker for metrics
            tracker.log_handoff_event(
                event_type="initiated",
                context=context_category,
                domain=domain,
                details={"person_name": person_name},
            )

            # Show exit celebration
            celebration = network.get_exit_celebration(chose_human=True)
            st.success(celebration)
            st.balloons()


def display_handoff_follow_up(pending_handoff: Dict):
    """Display handoff follow-up prompt (Phase 5)."""
    network = st.session_state.trusted_network
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    st.markdown("---")
    st.markdown("### Quick check-in")

    context = pending_handoff.get("context", "general")
    follow_up_prompts = loader.get_handoff_follow_up_prompts(context)
    prompt = (
        random.choice(follow_up_prompts) if follow_up_prompts else "Did you reach out to someone?"
    )

    st.markdown(f"*{prompt}*")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Yes, I reached out", use_container_width=True, type="primary"):
            st.session_state.show_handoff_outcome = True
            st.session_state.pending_handoff_for_outcome = pending_handoff
            tracker.mark_handoff_follow_up_shown(pending_handoff.get("datetime"))
            st.rerun()

    with col2:
        if st.button("Not yet", use_container_width=True):
            tracker.log_handoff_event(event_type="follow_up", context=context, outcome="not_yet")
            tracker.mark_handoff_follow_up_shown(pending_handoff.get("datetime"))
            celebration = network.get_handoff_celebration("not_yet")
            st.info(celebration)
            st.session_state.show_handoff_follow_up = False
            st.rerun()

    with col3:
        if st.button("Skip", use_container_width=True):
            tracker.mark_handoff_follow_up_shown(pending_handoff.get("datetime"))
            st.session_state.show_handoff_follow_up = False
            st.rerun()


def display_handoff_outcome():
    """Display outcome selection for handoff follow-up (Phase 5)."""
    network = st.session_state.trusted_network
    tracker = st.session_state.wellness_tracker
    pending = st.session_state.get("pending_handoff_for_outcome", {})
    context = pending.get("context", "general")

    st.markdown("---")
    st.markdown("### How did it go?")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Really helpful", use_container_width=True, type="primary"):
            tracker.log_handoff_event(
                event_type="reached_out", context=context, outcome="very_helpful"
            )
            tracker.log_handoff_event(
                event_type="outcome_reported", context=context, outcome="very_helpful"
            )
            celebration = network.get_handoff_celebration("very_helpful")
            st.success(celebration)
            st.balloons()
            st.session_state.show_handoff_outcome = False
            st.session_state.pending_handoff_for_outcome = None
            st.session_state.show_handoff_follow_up = False

    with col2:
        if st.button("Somewhat helpful", use_container_width=True):
            tracker.log_handoff_event(
                event_type="reached_out", context=context, outcome="somewhat_helpful"
            )
            tracker.log_handoff_event(
                event_type="outcome_reported", context=context, outcome="somewhat_helpful"
            )
            celebration = network.get_handoff_celebration("reached_out")
            st.success(celebration)
            st.session_state.show_handoff_outcome = False
            st.session_state.pending_handoff_for_outcome = None
            st.session_state.show_handoff_follow_up = False

    with col3:
        if st.button("Not very helpful", use_container_width=True):
            tracker.log_handoff_event(
                event_type="reached_out", context=context, outcome="not_helpful"
            )
            tracker.log_handoff_event(
                event_type="outcome_reported", context=context, outcome="not_helpful"
            )
            st.info("Not every conversation lands. The willingness to try is what counts.")
            st.session_state.show_handoff_outcome = False
            st.session_state.pending_handoff_for_outcome = None
            st.session_state.show_handoff_follow_up = False
