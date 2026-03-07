"""
empathySync - Help that knows when to stop
Main Streamlit application entry point

Core principle: Optimize for exit, not engagement.
Bridge people back to human connection.
"""

import streamlit as st
import sys
import json
import random
from pathlib import Path
from datetime import datetime, date
from typing import Dict

# Add src to path for imports
sys.path.append(str(Path(__file__).parent))

from config.settings import settings
from models.ai_wellness_guide import WellnessGuide
from models.risk_classifier import (
    RiskClassifier,
    INTENT_PRACTICAL,
    INTENT_PROCESSING,
    INTENT_EMOTIONAL,
    INTENT_CONNECTION,
)
from utils.helpers import setup_logging, validate_environment
from utils.wellness_tracker import WellnessTracker
from utils.trusted_network import TrustedNetwork
from utils.scenario_loader import get_scenario_loader
from utils.health_check import run_health_checks, has_critical_failures, auto_pull_model

# Pre-encode logo for inline HTML header (avoids st.columns layout issues)
import base64 as _b64

_logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
try:
    _LOGO_B64 = _b64.b64encode(_logo_path.read_bytes()).decode()
except Exception:
    _LOGO_B64 = ""

# Configure page
st.set_page_config(
    page_title="empathySync",
    page_icon="assets/logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished UI (works in both light and dark mode)
st.markdown(
    """
<style>
    /* -- Global typography -- */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    }

    /* -- Brand header -- */
    .es-brand {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .es-brand-logo {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        flex-shrink: 0;
    }
    .es-brand-name {
        font-size: 1.45rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        line-height: 1;
    }
    .es-brand-name span {
        color: #4A90D9;
    }

    /* -- Chat message text: fix horizontal overflow -- */
    .stChatMessage [data-testid="stMarkdownContainer"] {
        overflow-wrap: break-word !important;
        word-wrap: break-word !important;
        word-break: break-word !important;
        white-space: pre-wrap !important;
        max-width: 100% !important;
    }
    .stChatMessage [data-testid="stMarkdownContainer"] pre {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        overflow-x: auto !important;
    }
    .stChatMessage [data-testid="stMarkdownContainer"] p {
        max-width: 100% !important;
    }

    /* -- Chat bubbles -- */
    [data-testid="stChatMessage"] {
        padding: 0.85rem 1rem !important;
        border-radius: 12px !important;
        margin-bottom: 0.6rem !important;
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
    }
    /* User messages - subtle tint */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background: rgba(74, 144, 217, 0.06) !important;
    }
    /* Assistant messages - default bg */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: transparent !important;
    }

    /* -- Sidebar -- */
    section[data-testid="stSidebar"] .sidebar-header {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0.75rem 0 0.4rem 0;
        opacity: 0.5;
    }

    /* Sidebar button polish */
    section[data-testid="stSidebar"] .stButton > button {
        margin-bottom: 0.2rem;
        border-radius: 8px !important;
        font-size: 0.85rem;
        transition: all 0.15s ease;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        font-weight: 600;
    }

    /* -- Dividers -- */
    hr {
        margin: 0.75rem 0;
        border: none;
        border-top: 1px solid rgba(128, 128, 128, 0.2);
    }

    /* -- Reduce top padding on main area -- */
    .stMainBlockContainer {
        padding-top: 1.5rem !important;
    }

    /* -- Caption and small text -- */
    .stCaption, [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important;
        opacity: 0.55;
    }

    /* -- Chat input styling -- */
    [data-testid="stChatInput"] {
        border-radius: 12px !important;
    }
    [data-testid="stChatInput"] textarea {
        font-size: 0.92rem !important;
    }

    /* -- Hide default Streamlit title margin -- */
    h1 {
        margin-bottom: 0 !important;
    }

    /* -- Model badge in sidebar -- */
    .es-model-badge {
        display: inline-block;
        background: rgba(74, 144, 217, 0.12);
        font-size: 0.72rem;
        padding: 0.2rem 0.55rem;
        border-radius: 20px;
        font-weight: 500;
        letter-spacing: 0.01em;
        opacity: 0.7;
    }
</style>
""",
    unsafe_allow_html=True,
)


def display_safety_banner():
    """Display session safety banner when guardrails are active."""
    guide = st.session_state.wellness_guide

    if guide.last_policy_action:
        action = guide.last_policy_action
        policy_type = action.get("type", "")
        domain = action.get("domain", "")

        explanations = {
            "crisis_stop": "I detected crisis language and redirected to professional resources.",
            "harmful_stop": "I declined to engage with potentially harmful content.",
            "turn_limit_reached": f"We've reached the conversation limit for {domain} topics. This is by design.",
            "dependency_intervention": "I noticed a pattern that suggests it might be healthy to step back.",
            "high_risk_response": f"This topic ({domain}) is something a real person in your life can help with better than I can. My responses are shorter and I'm pointing toward people.",
            "cooldown_enforced": "Based on your usage pattern, I'm suggesting a break.",
        }

        explanation = explanations.get(policy_type, "A safety guardrail was activated.")
        st.info(f"**Why I responded this way:** {explanation}")


def display_transparency_panel():
    """Display the 'Why this response?' transparency panel (Phase 6)."""
    guide = st.session_state.wellness_guide
    loader = get_scenario_loader()

    # Only show if we have risk assessment data
    if not guide.last_risk_assessment:
        return

    assessment = guide.last_risk_assessment
    ui_labels = loader.get_transparency_ui_labels()

    # Get transparency settings
    settings = loader.get_transparency_settings()
    auto_expand = settings.get("auto_expand_on_policy", True)

    # Auto-expand if policy fired
    should_expand = auto_expand and guide.last_policy_action is not None

    with st.expander(ui_labels.get("panel_title", "Why this response?"), expanded=should_expand):
        # Phase 9.1: Determine mode once for all rows
        is_practical_technique = assessment.get("is_practical_technique", False)
        domain = assessment.get("domain", "logistics")
        is_practical = domain == "logistics" or is_practical_technique

        # Topic detected
        domain_info = loader.get_domain_explanation(domain)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{ui_labels.get('domain_label', 'Topic detected')}**")
        with col2:
            st.markdown(f"{domain_info.get('name', domain.title())}")
            st.caption(domain_info.get("description", ""))

        # Response mode
        mode = "practical" if is_practical else "reflective"
        mode_info = loader.get_mode_explanation(mode)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{ui_labels.get('mode_label', 'Response mode')}**")
        with col2:
            st.markdown(f"{mode_info.get('name', mode.title())}")
            if is_practical_technique and domain != "logistics":
                st.caption(f"Technique question in {domain} domain → full response")
            else:
                st.caption(mode_info.get("description", ""))

        # Risk level
        risk_weight = assessment.get("risk_weight", 1.0)
        risk_info = loader.get_risk_level_explanation(risk_weight)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{ui_labels.get('risk_level_label', 'Risk level')}**")
        with col2:
            st.markdown(f"{risk_info.get('name', 'Low')} ({risk_weight:.1f}/10)")
            if risk_info.get("description"):
                st.caption(risk_info.get("description"))

        # Policy action (if any)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{ui_labels.get('policy_label', 'Policy action')}**")
        with col2:
            if guide.last_policy_action:
                policy_type = guide.last_policy_action.get("type", "")
                policy_info = loader.get_policy_explanation(policy_type)
                st.markdown(f"{policy_info.get('name', policy_type)}")
                st.caption(policy_info.get("reason", ""))
                if policy_info.get("user_note"):
                    st.caption(f"*{policy_info.get('user_note')}*")
            else:
                st.markdown(ui_labels.get("none_triggered", "None triggered"))


def display_session_summary():
    """Display the end-of-session summary (Phase 6)."""
    guide = st.session_state.wellness_guide
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    summary_config = loader.get_session_summary_config()
    ui_labels = loader.get_transparency_ui_labels()

    # Get session data
    session_summary = guide.get_session_summary()
    turn_count = session_summary.get("turn_count", 0)
    domains_touched = session_summary.get("domains_touched", [])
    max_risk = session_summary.get("max_risk_weight", 0)
    policy_action = session_summary.get("last_policy_action")

    # Calculate duration
    duration_minutes = 0
    if hasattr(st.session_state, "session_start"):
        duration_minutes = int(
            (datetime.now() - st.session_state.session_start).total_seconds() / 60
        )

    # Check thresholds - don't show for very short sessions
    settings = loader.get_transparency_settings()
    min_duration = settings.get("summary_min_duration", 3)
    min_turns = settings.get("summary_min_turns", 2)

    if duration_minutes < min_duration and turn_count < min_turns:
        return

    st.markdown(f"### {summary_config.get('header', 'Session Summary')}")

    sections = summary_config.get("sections", {})
    practical_turns = sum(1 for d in domains_touched if d == "logistics")
    reflective_turns = len(domains_touched) - practical_turns

    # Compact summary
    st.markdown(
        f"**{duration_minutes} min** · {turn_count} turns · "
        f"{practical_turns} practical, {reflective_turns} reflective"
    )

    # Topics
    if domains_touched:
        unique_domains = list(set(domains_touched))
        domain_names = []
        for domain in unique_domains:
            domain_info = loader.get_domain_explanation(domain)
            domain_names.append(domain_info.get("name", domain.title()))
        st.caption(f"Topics: {', '.join(domain_names)}")

    # Risk + policy
    risk_info = loader.get_risk_level_explanation(max_risk)
    risk_line = f"Peak risk: {risk_info.get('name', 'Low')} ({max_risk:.0f}/10)"
    if policy_action:
        policy_info = loader.get_policy_explanation(policy_action.get("type", ""))
        risk_line += f" · Guardrail: {policy_info.get('name', 'Yes')}"
    st.caption(risk_line)

    # Footer message
    session_type = "all_practical"
    if reflective_turns > practical_turns:
        session_type = "mostly_reflective"
    elif practical_turns > 0 and reflective_turns > 0:
        session_type = "mixed"
    if policy_action:
        session_type = "policy_fired"
    if duration_minutes > 30:
        session_type = "long_session"

    footer_messages = loader.get_session_summary_footer(session_type)
    if footer_messages:
        st.info(random.choice(footer_messages))

    col1, col2 = st.columns(2)
    with col1:
        export_data = {
            "session_date": datetime.now().isoformat(),
            "duration_minutes": duration_minutes,
            "turn_count": turn_count,
            "domains_touched": list(set(domains_touched)),
            "max_risk_weight": max_risk,
            "policy_action": policy_action.get("type") if policy_action else None,
        }
        st.download_button(
            ui_labels.get("export_summary", "Export summary"),
            data=json.dumps(export_data, indent=2),
            file_name=f"session_summary_{date.today()}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col2:
        if st.button(ui_labels.get("close_summary", "Close"), use_container_width=True):
            st.session_state.show_session_summary = False
            st.rerun()


def display_usage_health():
    """Display usage health indicators in sidebar."""
    tracker = st.session_state.wellness_tracker
    summary = tracker.get_wellness_summary()

    sessions_today = summary.get("sessions_today", 0)
    minutes_today = summary.get("minutes_today", 0)
    dependency_score = summary.get("dependency_score", 0)

    if sessions_today > 0 or minutes_today > 0:
        st.caption(f"Today: {sessions_today} sessions, {minutes_today} min")

    if dependency_score >= 7:
        st.error("Consider taking a break. Your usage pattern suggests over-reliance.")
    elif dependency_score >= 5:
        st.warning("You've been here often. Consider talking to someone you trust.")
    elif sessions_today >= 3:
        st.caption("Multiple sessions today. How are you feeling about that?")

    # Only show late-night warning if there's a pattern (2+ late sessions this week)
    # Not just for being up late once
    if tracker.is_late_night_session() and tracker.get_late_night_sessions_this_week() >= 2:
        st.caption("You've been here late at night a few times. Everything okay?")


def display_my_patterns_dashboard():
    """
    Display the 'My Patterns' dashboard (Phase 7).

    Shows sensitive vs practical usage trends, anti-engagement score,
    and week-over-week comparisons. Only sensitive usage counts toward
    the reliance score - practical task usage is just using a tool.
    """
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    st.markdown("### My Patterns")

    try:
        dashboard = tracker.get_my_patterns_dashboard()
    except Exception:
        st.caption("Not enough data yet. Check back after a few sessions.")
        return

    # Summary message based on health status
    health_status = dashboard.get("health_status", "moderate")
    summary = dashboard.get("summary", "")

    if health_status == "healthy":
        st.success(summary)
    elif health_status == "concerning":
        st.warning(summary)
    else:
        st.info(summary)

    # Week comparison — compact format
    this_week = dashboard.get("this_week", {})
    last_week = dashboard.get("last_week", {})
    trends = dashboard.get("trends", {})

    def trend_line(label, key, good_direction="down"):
        """Render a single trend line."""
        trend_data = trends.get(key, {})
        icon = trend_data.get("icon", "→")
        this_val = this_week.get(key, 0)
        last_val = last_week.get(key, 0)
        status = trend_data.get("status", "stable")
        warning = " ⚠️" if status == "concerning" else ""
        return f"- {label}: **{this_val}** {icon} (was {last_val}){warning}"

    lines = [
        trend_line("Sensitive topics", "sensitive_topics"),
        trend_line("Connection seeking", "connection_seeking"),
        trend_line("Human reach-outs", "human_reach_outs", good_direction="up"),
        trend_line("Did it myself", "did_it_myself", good_direction="up"),
    ]
    st.markdown("\n".join(lines))

    practical_count = this_week.get("practical_tasks", 0)
    if practical_count > 0:
        st.caption(f"Practical tasks this week: {practical_count} (just using a tool)")

    st.markdown("---")

    # Reliance score — compact
    anti_engagement = dashboard.get("anti_engagement", {})
    score = anti_engagement.get("score", 0)
    level = anti_engagement.get("level", "moderate")
    label = anti_engagement.get("label", "Unknown")
    message = anti_engagement.get("message", "")

    if level in ["excellent", "good"]:
        st.success(f"**Reliance: {score}/10** — {label}")
    elif level == "moderate":
        st.warning(f"**Reliance: {score}/10** — {label}")
    else:
        st.error(f"**Reliance: {score}/10** — {label}")

    st.caption(message)

    # Close button
    if st.button("Close", use_container_width=True, key="close_patterns"):
        st.session_state.show_my_patterns = False
        st.rerun()


def display_self_report_prompt():
    """
    Display a self-report prompt when conditions are met (Phase 7.2).

    Non-intrusive prompts to help users reflect on their usage.
    """
    tracker = st.session_state.wellness_tracker

    should_show, prompt_config = tracker.should_show_self_report()

    if not should_show or not prompt_config:
        return

    prompt_type = prompt_config.get("type", "")
    question = prompt_config.get("question", "")
    options = prompt_config.get("options", [])

    with st.expander("Quick check-in", expanded=True):
        st.markdown(f"**{question}**")

        for opt in options:
            if st.button(opt["label"], key=f"self_report_{opt['value']}", use_container_width=True):
                tracker.record_self_report(prompt_type, opt["value"])

                # Show appropriate follow-up
                if opt["value"] == "helpful":
                    st.success("Glad to hear that.")
                elif opt["value"] == "too_much":
                    st.info("Taking breaks is healthy. Consider reaching out to someone you trust.")
                elif opt["value"] == "skip":
                    st.caption("No problem.")

                st.rerun()


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
        st.caption("No specific services—just types of places to search locally.")

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


def display_intent_check_in():
    """Subtle connection nudge shown occasionally at session start (Phase 4).

    Replaces the 3-button gate. The classifier handles practical vs reflective
    intent automatically. The only path worth preserving explicitly is connection-
    seeking, which the classifier can't catch before the first message.
    """
    tracker = st.session_state.wellness_tracker

    col1, col2 = st.columns([4, 1])
    with col1:
        st.caption("Just here to talk? Someone in your life would be better for that than I am.")
    with col2:
        if st.button("Find them →", use_container_width=True):
            tracker.record_session_intent(INTENT_CONNECTION, was_check_in=True)
            st.session_state.conversation_session.session_intent = INTENT_CONNECTION
            st.session_state.show_connection_redirect = True
            st.session_state.show_intent_check_in = False
            st.rerun()


def display_connection_redirect():
    """Display gentle redirect when user indicates they just want to talk."""
    tracker = st.session_state.wellness_tracker
    network = st.session_state.trusted_network
    loader = get_scenario_loader()

    st.markdown("---")

    # Get response from scenarios
    responses = loader.get_connection_responses("explicit")
    if responses:
        response = random.choice(responses)
    else:
        response = (
            "I'm here to help with tasks and thinking through things, but I'm not "
            "great at just chatting. Is there someone you could reach out to right now? "
            "Or if there's something specific on your mind, I'm happy to help you think through it."
        )

    st.info(response)

    # Show trusted people if available
    people = network.get_all_people()
    if people:
        st.markdown("**Your trusted people:**")
        for person in people[:3]:  # Show top 3
            st.markdown(f"- **{person['name']}** ({person.get('relationship', '')})")

        st.markdown("---")
        if st.button("I'll reach out to someone", type="primary", use_container_width=True):
            # Log this as a successful redirect
            tracker.log_policy_event(
                policy_type="connection_redirect",
                domain="connection_seeking",
                risk_weight=0,
                action_taken="User chose to reach out to human",
            )
            network.log_reach_out("someone", method="message", topic="general")
            st.balloons()
            st.success("That's the right call. Take care.")
            st.session_state.show_connection_redirect = False
            st.rerun()
    else:
        st.markdown("**Consider:** Who in your life could you reach out to right now?")

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Actually, I have something specific", use_container_width=True):
            st.session_state.conversation_session.session_intent = INTENT_PRACTICAL
            st.session_state.show_connection_redirect = False
            st.rerun()
    with col2:
        if st.button("Set up trusted network", use_container_width=True):
            st.session_state.show_connection_redirect = False
            st.session_state.show_network_setup = True
            st.rerun()


def display_intent_shift_prompt(shift_info: dict):
    """Display prompt when intent shift is detected mid-session."""
    st.markdown("---")
    st.info(
        "It sounds like this became about more than just the task. "
        "Want to pause and talk about what's coming up? "
        "Or would you prefer I just help with the original task?"
    )

    session = st.session_state.conversation_session
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Let's talk about what's coming up", use_container_width=True):
            session.acknowledge_intent_shift(accept_shift=True)
            st.rerun()
    with col2:
        if st.button("Just help with the task", use_container_width=True):
            session.acknowledge_intent_shift(accept_shift=False)
            st.rerun()


def display_graduation_prompt(category: str, prompt_text: str):
    """Display a graduation prompt suggesting skill-building."""
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    st.markdown("---")
    st.info(prompt_text)

    session = st.session_state.conversation_session
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Show me some tips", use_container_width=True, type="primary"):
            st.session_state.show_skill_tips = category
            session.accept_graduation()
            st.rerun()
    with col2:
        if st.button("Just help me", use_container_width=True):
            session.dismiss_graduation()
            st.rerun()


def display_skill_tips(category: str):
    """Display skill tips for a task category."""
    loader = get_scenario_loader()
    tips = loader.get_skill_tips(category)

    if not tips:
        return

    st.markdown("---")
    st.markdown("### Quick tips for doing this yourself")

    for tip in tips:
        with st.expander(tip.get("title", "Tip"), expanded=True):
            st.markdown(tip.get("content", ""))

    st.markdown("---")
    if st.button("Got it, thanks!", use_container_width=True):
        st.session_state.show_skill_tips = None
        st.rerun()


def display_independence_button():
    """Display the 'I did it myself!' button in sidebar."""
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    # Get button labels
    labels = loader.get_independence_button_labels()
    label = labels[0] if labels else "I did it myself!"

    if st.button(label, use_container_width=True, help="Did you complete a task on your own?"):
        st.session_state.show_independence_form = True
        st.rerun()


def display_independence_form():
    """Display form for recording independence."""
    tracker = st.session_state.wellness_tracker
    loader = get_scenario_loader()

    st.markdown("### Nice work!")
    st.markdown("What did you do on your own?")

    categories = loader.get_graduation_categories()
    category_options = ["general"] + list(categories.keys())
    category_labels = {
        "general": "Something else",
        "email_drafting": "Wrote an email",
        "code_help": "Solved a coding problem",
        "explanations": "Figured something out",
        "writing_general": "Wrote something",
        "summarizing": "Summarized content",
    }

    category = st.selectbox(
        "Category",
        category_options,
        format_func=lambda x: category_labels.get(x, x.replace("_", " ").title()),
        label_visibility="collapsed",
    )

    notes = st.text_input("Notes (optional)", placeholder="e.g., 'Wrote the meeting recap myself'")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Record it!", use_container_width=True, type="primary"):
            tracker.record_independence(category, notes)

            # Show celebration
            celebrations = loader.get_independence_celebrations()
            if celebrations:
                celebration = random.choice(celebrations)
                st.success(celebration)

            # Check for milestone
            stats = tracker.get_independence_stats()
            if stats.get("is_milestone"):
                st.balloons()
                count = stats.get("total_recent", 0)
                st.info(
                    f"You've done {count} things on your own recently. Your skills are growing."
                )

            st.session_state.show_independence_form = False
            st.rerun()

    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_independence_form = False
            st.rerun()


def display_reality_check():
    """Display the reality check panel."""
    tracker = st.session_state.wellness_tracker
    network = st.session_state.trusted_network

    signals = tracker.calculate_dependency_signals()
    connection_health = network.get_connection_health()

    st.markdown("### Pause and reflect")

    st.caption(
        "This is software, not a person. It reflects patterns in text — "
        "it doesn't truly know you."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Sessions today", signals["sessions_today"])
        st.metric("This week", signals["sessions_this_week"])
        if signals["late_night_sessions"] > 0:
            st.metric("Late night", signals["late_night_sessions"])
    with col2:
        st.metric("Trusted people", connection_health["total_trusted_people"])
        st.metric("Reach-outs", connection_health["reach_outs_this_week"])
        if connection_health["neglected_contacts"] > 0:
            st.metric("Haven't contacted", connection_health["neglected_contacts"])

    if signals["warnings"]:
        for warning in signals["warnings"]:
            st.caption(f"- {warning}")

    reflection = network.get_reflection_prompt()
    st.markdown(f"*{reflection}*")

    if st.button("I understand", use_container_width=True):
        st.session_state.show_reality_check = False
        st.rerun()


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
    should_cooldown, cooldown_reason = tracker.should_enforce_cooldown()
    if should_cooldown:
        st.warning(cooldown_reason)

        people = network.get_all_people()
        if people:
            person = random.choice(people)
            st.markdown(f"**Consider calling {person['name']}** instead of being here.")
        else:
            st.markdown("**Consider:** Who could you call right now?")

        for message in session.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        return

    # Display existing messages
    for message in session.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # === ONE panel at a time in main area (priority order) ===
    # Everything is opt-in via sidebar — nothing auto-opens
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
    elif prompt := st.chat_input("What are you thinking through?"):
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process message through ConversationSession streaming pipeline
        with st.chat_message("assistant"):
            result = session.process_message_stream(prompt)
            if result.is_streaming:
                st.write_stream(result.response_stream)
                result = session.finalize_stream()
            else:
                st.markdown(result.response)

        # Sync messages reference for backward compatibility
        st.session_state.messages = session.messages

        if result.should_rerun:
            st.rerun()


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


def display_lock_warning():
    """
    Check device lock status and configure read-only mode if needed (Phase 11).

    Instead of blocking the entire app when another device has the lock,
    we allow read-only viewing but disable write operations. This provides
    a better UX while maintaining data safety.

    Returns:
        True if locked by another device (app in read-only mode)
        False if we have the lock or lock checking is disabled
    """
    from utils.write_gate import set_read_only

    if not settings.ENABLE_DEVICE_LOCK:
        st.session_state.read_only_mode = False
        set_read_only(False)
        return False

    # Only check lock status once per session
    if "lock_status_checked" in st.session_state:
        return st.session_state.get("read_only_mode", False)

    try:
        from utils.lockfile import check_lock_status, acquire_lock

        status = check_lock_status()
        st.session_state.lock_status_checked = True

        if status["locked_by_other"]:
            st.session_state.read_only_mode = True
            st.session_state.lock_status = status
            set_read_only(True)  # Enable write gate
            return True
        else:
            # Try to acquire lock
            if not status["locked_by_us"]:
                acquire_lock()
            st.session_state.read_only_mode = False
            set_read_only(False)  # Disable write gate
            return False

    except Exception as e:
        # If lock check fails, log and continue (don't block the app)
        import logging

        logging.warning(f"Lock file check failed: {e}")
        st.session_state.lock_status_checked = True
        st.session_state.read_only_mode = False
        set_read_only(False)
        return False


def display_lock_banner():
    """Display a persistent banner when in read-only mode due to device lock."""
    if not st.session_state.get("read_only_mode"):
        return

    status = st.session_state.get("lock_status", {})
    hostname = status.get("hostname", "another device")
    started = status.get("started_at", "unknown time")

    # Parse started time for friendly display
    try:
        started_dt = datetime.fromisoformat(started)
        started = started_dt.strftime("%I:%M %p on %b %d")
    except (ValueError, TypeError):
        pass

    col1, col2, col3 = st.columns([5, 2, 1])
    with col1:
        st.warning(
            f"**Read-only mode**: empathySync is open on {hostname} (since {started}). "
            f"Writes are blocked to prevent sync conflicts. Close it there first."
        )
    with col2:
        if st.button(
            "Take Over",
            type="primary",
            help="Force access - use only if the other device is unavailable",
        ):
            handle_lock_takeover()
    with col3:
        if st.button("Dismiss"):
            st.session_state.lock_banner_dismissed = True
            st.rerun()


def handle_lock_takeover():
    """Handle user clicking 'Take Over' to force lock acquisition."""
    try:
        from utils.lockfile import acquire_lock
        from utils.write_gate import set_read_only

        if acquire_lock(force=True):
            st.session_state.read_only_mode = False
            st.session_state.lock_status = None
            set_read_only(False)  # Re-enable writes
            st.success("Lock acquired. You now have full access.")
            st.rerun()
    except Exception as e:
        st.error(f"Failed to take over lock: {e}")


def is_read_only():
    """Check if the app is in read-only mode due to device lock."""
    return st.session_state.get("read_only_mode", False)


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
    # UI toggle state (stays in st.session_state — not conversation logic)
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

    # Intent check-in removed from main area — the risk classifier detects intent
    # from the first message naturally. Less friction, same result.

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
        # Get current domain if available for context-aware signposts
        current_domain = None
        if st.session_state.messages:
            guide = st.session_state.wellness_guide
            if hasattr(guide, "_session_state") and guide._session_state.get("domains"):
                # Get most recent domain
                current_domain = (
                    guide._session_state["domains"][-1] if guide._session_state["domains"] else None
                )

        with st.expander("No trusted network yet — find your people", expanded=False):
            display_building_your_network(domain=current_domain)

    # Sidebar - clean, minimal, restrained
    with st.sidebar:
        wellness_mode = "Balanced"

        # Brand at top of sidebar
        _logo_html = (
            f'<img src="data:image/png;base64,{_LOGO_B64}" ' f'alt="logo" class="es-brand-logo">'
            if _LOGO_B64
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
        if st.button("New Chat", use_container_width=True, type="primary"):
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

        # Subtle usage stats
        display_usage_health()

        # Show active model as badge
        if settings.OLLAMA_MODEL:
            st.markdown(
                f'<span class="es-model-badge">{settings.OLLAMA_MODEL}</span>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # === TOOLS - toggle panels (only one open at a time) ===
        st.markdown('<div class="sidebar-header">Tools</div>', unsafe_allow_html=True)
        reality_active = st.session_state.get("show_reality_check", False)
        network_active = st.session_state.get("show_network_setup", False)
        patterns_active = st.session_state.get("show_my_patterns", False)

        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "My People",
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
                "My Patterns",
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

        st.markdown("---")

        # === SECONDARY ACTIONS ===
        # Reality Check - less prominent, below the main tools
        if not reality_active:
            if st.button(
                "Reality Check",
                use_container_width=True,
                help="Am I relying on this too much?",
            ):
                st.session_state.show_reality_check = True
                st.session_state.show_network_setup = False
                st.session_state.show_my_patterns = False
                st.rerun()

        # Transparency toggle — opt-in for power users
        guide = st.session_state.wellness_guide
        if guide.last_risk_assessment and st.session_state.messages:
            transparency_active = st.session_state.get("show_transparency", False)
            if st.button(
                "Why this response?" if not transparency_active else "Hide details",
                use_container_width=True,
            ):
                st.session_state.show_transparency = not transparency_active
                st.rerun()

        # Reach out — only show when conversation is active and in sensitive domain
        current_domain = "general"
        if guide.last_risk_assessment:
            current_domain = guide.last_risk_assessment.get("domain", "general")
        if current_domain in ["relationships", "money", "health", "spirituality", "emotional"]:
            with st.expander("Reach Out to Someone", expanded=False):
                display_bring_someone_in(current_domain)

        # Independence button — only show when not in a panel
        if not any([reality_active, network_active, patterns_active]):
            if st.session_state.get("show_independence_form"):
                display_independence_form()
            else:
                display_independence_button()

        st.markdown("---")

        # === SESSION & DATA ===
        st.markdown('<div class="sidebar-header">Data</div>', unsafe_allow_html=True)
        with st.expander("Session & Data", expanded=False):
            # Session summary (only if conversation happened)
            if guide.session_turn_count > 0:
                if st.button(
                    "View Session Summary",
                    use_container_width=True,
                ):
                    st.session_state.show_session_summary = True
                    st.rerun()

            # Export
            tracker = st.session_state.wellness_tracker
            data = tracker._load_data()
            st.download_button(
                "Export Data",
                data=json.dumps(data, indent=2),
                file_name=f"empathysync_{date.today()}.json",
                mime="application/json",
                use_container_width=True,
            )

            st.caption("All data stays on your device.")

            # Reset — behind confirmation
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

    # Main chat interface
    display_chat_interface(wellness_mode)


if __name__ == "__main__":
    main()
