"""Display panels and UI components for empathySync. Transparency, patterns, reality check, session summary, and more."""

import json
import random
from datetime import datetime, date

import streamlit as st

from utils.scenario_loader import get_scenario_loader
from models.risk_classifier import INTENT_PRACTICAL, INTENT_CONNECTION


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
