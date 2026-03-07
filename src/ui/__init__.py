"""
empathySync UI package.
Extracted from app.py (Phase 16.12) for maintainability.
"""

from ui.styles import LOGO_B64, apply_page_config, apply_custom_css
from ui.lock import is_read_only, display_lock_warning, display_lock_banner, handle_lock_takeover
from ui.chat import display_chat_interface
from ui.sidebar import render_sidebar, save_session_on_end
from ui.panels import (
    display_safety_banner,
    display_transparency_panel,
    display_session_summary,
    display_usage_health,
    display_my_patterns_dashboard,
    display_self_report_prompt,
    display_intent_check_in,
    display_connection_redirect,
    display_intent_shift_prompt,
    display_graduation_prompt,
    display_skill_tips,
    display_independence_button,
    display_independence_form,
    display_reality_check,
)
from ui.network import (
    display_trusted_network_setup,
    display_building_your_network,
    display_bring_someone_in,
    display_handoff_follow_up,
    display_handoff_outcome,
)

__all__ = [
    "LOGO_B64",
    "apply_page_config",
    "apply_custom_css",
    "is_read_only",
    "display_lock_warning",
    "display_lock_banner",
    "handle_lock_takeover",
    "display_chat_interface",
    "render_sidebar",
    "save_session_on_end",
    "display_safety_banner",
    "display_transparency_panel",
    "display_session_summary",
    "display_usage_health",
    "display_my_patterns_dashboard",
    "display_self_report_prompt",
    "display_intent_check_in",
    "display_connection_redirect",
    "display_intent_shift_prompt",
    "display_graduation_prompt",
    "display_skill_tips",
    "display_independence_button",
    "display_independence_form",
    "display_reality_check",
    "display_trusted_network_setup",
    "display_building_your_network",
    "display_bring_someone_in",
    "display_handoff_follow_up",
    "display_handoff_outcome",
]
