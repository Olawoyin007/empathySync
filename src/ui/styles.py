"""
UI styles and theming for empathySync.
CSS, page configuration, and logo encoding.
"""

import base64
from pathlib import Path

import streamlit as st


# Pre-encode logo for inline HTML header
_logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
try:
    LOGO_B64 = base64.b64encode(_logo_path.read_bytes()).decode()
except Exception:
    LOGO_B64 = ""


def apply_page_config():
    """Configure Streamlit page settings. Must be called first."""
    st.set_page_config(
        page_title="empathySync",
        page_icon="assets/logo.png",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_custom_css():
    """Inject custom CSS for polished UI (works in both light and dark mode)."""
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
