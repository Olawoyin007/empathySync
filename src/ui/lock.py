"""
Device lock UI components for empathySync.
Lock warnings, banners, takeover, and read-only state.
"""

import streamlit as st
from datetime import datetime

from config.settings import settings


def is_read_only():
    """Check if the app is in read-only mode due to device lock."""
    return st.session_state.get("read_only_mode", False)


def display_lock_warning():
    """
    Check device lock status and configure read-only mode if needed (Phase 11).

    Instead of blocking the entire app when another device has the lock,
    we allow read-only viewing but disable write operations.
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
            set_read_only(True)
            return True
        else:
            if not status["locked_by_us"]:
                acquire_lock()
            st.session_state.read_only_mode = False
            set_read_only(False)
            return False

    except Exception as e:
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
            set_read_only(False)
            st.success("Lock acquired. You now have full access.")
            st.rerun()
    except Exception as e:
        st.error(f"Failed to take over lock: {e}")
