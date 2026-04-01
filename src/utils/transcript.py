"""
Conversation transcript formatting utilities.

Converts empathySync message history into human-readable export formats.
Kept as pure functions (no Streamlit or IO imports) for easy testing.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional


def generate_markdown_transcript(
    messages: List[Dict[str, str]],
    exported_at: Optional[datetime] = None,
    session_turns: Optional[int] = None,
    domains: Optional[List[str]] = None,
    app_version: str = "",
) -> str:
    """Convert a list of chat messages into a Markdown transcript.

    Args:
        messages: List of dicts with 'role' ('user' or 'assistant') and 'content'.
        exported_at: Timestamp for the export header. Defaults to now.
        session_turns: Optional turn count for the footer.
        domains: Optional list of domains touched during the session.
        app_version: App version string for the footer (e.g. '1.5.0').

    Returns:
        A formatted Markdown string ready for download.
    """
    if exported_at is None:
        exported_at = datetime.now()

    date_str = exported_at.strftime("%Y-%m-%d at %H:%M")
    lines: List[str] = []

    # Header
    lines.append("# empathySync - Conversation Transcript")
    lines.append("")
    lines.append(f"*Exported: {date_str}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not messages:
        lines.append("*No messages in this session.*")
        lines.append("")
    else:
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()

            if role == "user":
                label = "**You**"
            elif role == "assistant":
                label = "**empathySync**"
            else:
                continue

            lines.append(label)
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

    # Footer
    footer_parts = []
    if session_turns is not None:
        footer_parts.append(f"{session_turns} turns")
    if domains:
        footer_parts.append("topics: " + ", ".join(domains))

    footer_meta = " | ".join(footer_parts)
    version_note = f"empathySync v{app_version}" if app_version else "empathySync"
    footer = f"*{footer_meta + ' | ' if footer_meta else ''}{version_note} - local-first, private by design.*"
    lines.append(footer)

    return "\n".join(lines)
