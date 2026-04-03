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
        gap: 0.6rem;
        padding: 0.25rem 0;
    }
    .es-brand-logo {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(74, 144, 217, 0.25);
    }
    .es-brand-name {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        line-height: 1;
        color: rgba(230, 237, 243, 0.92);
    }
    .es-brand-name span {
        color: #4A90D9;
    }

    /* -- Constrain main content width for readability -- */
    .stMainBlockContainer > div {
        max-width: 820px;
        margin-left: auto;
        margin-right: auto;
    }

    /* -- Chat message text: fix horizontal overflow -- */
    .stChatMessage [data-testid="stMarkdownContainer"],
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
        overflow-wrap: break-word !important;
        word-wrap: break-word !important;
        word-break: break-word !important;
        max-width: 100% !important;
    }
    /* Only pre/code blocks preserve whitespace literally */
    .stChatMessage [data-testid="stMarkdownContainer"] pre,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] pre {
        white-space: pre-wrap !important;
        word-break: break-all !important;
        overflow-x: auto !important;
    }
    .stChatMessage [data-testid="stMarkdownContainer"] p,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
        max-width: 100% !important;
        line-height: 1.7;
    }
    /* Better list styling in chat */
    .stChatMessage ol, .stChatMessage ul,
    [data-testid="stChatMessage"] ol, [data-testid="stChatMessage"] ul,
    [data-testid="stMarkdownContainer"] ol, [data-testid="stMarkdownContainer"] ul {
        line-height: 1.6;
        padding-left: 1.5rem;
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
    }
    .stChatMessage li, [data-testid="stChatMessage"] li,
    [data-testid="stMarkdownContainer"] li {
        margin-bottom: 0.4rem;
        padding-left: 0.25rem;
    }
    /* Keep list item content inline with numbers */
    .stChatMessage li p, [data-testid="stChatMessage"] li p,
    [data-testid="stMarkdownContainer"] li p {
        display: inline !important;
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }

    /* -- Chat bubbles (multiple selectors for version compat) -- */
    .stChatMessage,
    [data-testid="stChatMessage"] {
        padding: 1.1rem 1.25rem !important;
        border-radius: 14px !important;
        margin-bottom: 0.85rem !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        background: rgba(255, 255, 255, 0.025) !important;
        transition: background 0.2s ease;
    }
    /* User messages - distinct blue tint */
    .stChatMessage:has([data-testid="chatAvatarIcon-user"]),
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
    .stChatMessage.st-emotion-cache-user,
    [data-testid="stChatMessageContent-user"] {
        background: rgba(74, 144, 217, 0.09) !important;
        border: 1px solid rgba(74, 144, 217, 0.15) !important;
    }
    /* Assistant messages - subtle elevated card */
    .stChatMessage:has([data-testid="chatAvatarIcon-assistant"]),
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: rgba(255, 255, 255, 0.035) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* Chat avatar polish */
    .stChatMessage [data-testid*="chatAvatarIcon"],
    [data-testid="stChatMessage"] [data-testid*="chatAvatarIcon"] {
        border-radius: 50% !important;
    }

    /* -- Sidebar -- */
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    /* Prevent button labels from breaking mid-word when sidebar is narrow */
    section[data-testid="stSidebar"] .stButton > button p,
    section[data-testid="stSidebar"] .stButton > button span:not([data-testid]) {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* Sidebar buttons - compact with icon alignment */
    section[data-testid="stSidebar"] .stButton > button {
        margin-bottom: 0.15rem;
        border-radius: 8px !important;
        font-size: 0.82rem;
        padding-top: 0.4rem !important;
        padding-bottom: 0.4rem !important;
        transition: all 0.2s ease;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        border-color: rgba(74, 144, 217, 0.25) !important;
        background: rgba(74, 144, 217, 0.07) !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        font-weight: 600;
        background: linear-gradient(135deg, #3a7bd5, #4A90D9) !important;
        border: none !important;
        box-shadow: 0 2px 10px rgba(74, 144, 217, 0.25);
        text-align: center !important;
        justify-content: center !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #4A90D9, #5ba0e9) !important;
        box-shadow: 0 3px 14px rgba(74, 144, 217, 0.35);
    }

    /* -- Dividers -- */
    hr {
        margin: 0.85rem 0;
        border: none;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
    }

    /* -- Hide Streamlit deploy button -- */
    [data-testid="stAppDeployButton"] {
        display: none !important;
    }

    /* -- Top padding on main area (clear Streamlit toolbar) -- */
    .stMainBlockContainer {
        padding-top: 3.5rem !important;
    }
    .stAppHeader {
        background: transparent !important;
    }

    /* -- Caption and small text -- */
    .stCaption, [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important;
        opacity: 0.45;
    }

    /* -- Chat input styling -- */
    [data-testid="stChatInput"],
    .stChatInput {
        border-radius: 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        background: rgba(255, 255, 255, 0.04) !important;
        max-width: 820px;
        margin-left: auto;
        margin-right: auto;
    }
    [data-testid="stChatInput"] textarea,
    .stChatInput textarea {
        font-size: 0.92rem !important;
        line-height: 1.5 !important;
    }
    /* Input container - subtle glow on focus */
    [data-testid="stChatInput"]:focus-within,
    .stChatInput:focus-within {
        border-color: rgba(74, 144, 217, 0.4) !important;
        box-shadow: 0 0 0 2px rgba(74, 144, 217, 0.12) !important;
    }

    /* -- Bottom chat input area (Streamlit sticks it to bottom) -- */
    .stBottom > div {
        max-width: 820px;
        margin-left: auto;
        margin-right: auto;
    }

    /* -- Hide default Streamlit title margin -- */
    h1 {
        margin-bottom: 0 !important;
    }

    /* -- Model badge in sidebar -- */
    .es-model-badge {
        display: inline-block;
        background: rgba(74, 144, 217, 0.1);
        color: rgba(74, 144, 217, 0.85);
        font-size: 0.72rem;
        padding: 0.22rem 0.6rem;
        border-radius: 20px;
        font-weight: 500;
        letter-spacing: 0.01em;
        border: 1px solid rgba(74, 144, 217, 0.15);
    }

    /* -- Welcome / empty state -- */
    .es-welcome {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 55vh;
        text-align: center;
        padding: 2rem;
        opacity: 0.85;
    }
    .es-welcome-logo {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 20px rgba(74, 144, 217, 0.2);
    }
    .es-welcome h2 {
        font-size: 1.4rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: rgba(230, 237, 243, 0.9);
    }
    .es-welcome p {
        font-size: 0.92rem;
        color: rgba(230, 237, 243, 0.45);
        max-width: 420px;
        line-height: 1.6;
    }
    .es-welcome-hint {
        margin-top: 1.5rem;
        font-size: 0.78rem;
        color: rgba(230, 237, 243, 0.3);
    }

    /* -- Network banner -- */
    .es-network-banner {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.55rem 0.85rem;
        background: rgba(74, 144, 217, 0.06);
        border: 1px solid rgba(74, 144, 217, 0.12);
        border-radius: 10px;
        font-size: 0.82rem;
        color: rgba(230, 237, 243, 0.65);
        margin-bottom: 0.5rem;
    }

    /* -- Expander polish -- */
    .streamlit-expanderHeader {
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        border-radius: 10px !important;
    }
    details[data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 12px !important;
        background: rgba(255, 255, 255, 0.02) !important;
    }
    /* Tighter spacing inside expanders */
    details[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {
        margin-bottom: 0.1rem !important;
    }
    details[data-testid="stExpander"] [data-testid="stCaptionContainer"] {
        margin-bottom: 0.4rem !important;
    }

    /* -- Metric polish -- */
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 0.75rem !important;
    }

    /* -- Info/Warning/Success box polish -- */
    .stAlert {
        border-radius: 12px !important;
    }

    /* -- Scrollbar polish (webkit) -- */
    ::-webkit-scrollbar {
        width: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.2);
    }
</style>
""",
        unsafe_allow_html=True,
    )
