"""
Tests for src/utils/write_gate.py

Covers:
- Read-only mode toggling
- WriteBlockedError exception
- @require_write decorator behavior
- check_write_permission() explicit checks
"""

import pytest

from utils.write_gate import (
    WriteBlockedError,
    check_write_permission,
    is_read_only,
    is_write_allowed,
    require_write,
    set_read_only,
)


@pytest.fixture(autouse=True)
def reset_write_gate():
    """Ensure clean state before and after each test."""
    set_read_only(False)
    yield
    set_read_only(False)


class TestWriteGateState:
    """Tests for read-only mode state management."""

    # THREAT_MODEL.md control: Write gate
    def test_default_state_allows_writes(self):
        assert is_write_allowed() is True
        assert is_read_only() is False

    # THREAT_MODEL.md control: Write gate
    def test_set_read_only_blocks_writes(self):
        set_read_only(True)
        assert is_write_allowed() is False
        assert is_read_only() is True

    def test_toggle_read_only_restores_writes(self):
        set_read_only(True)
        assert is_read_only() is True
        set_read_only(False)
        assert is_write_allowed() is True
        assert is_read_only() is False


class TestRequireWriteDecorator:
    """Tests for the @require_write decorator."""

    def test_allows_execution_when_writable(self):
        @require_write
        def save_data():
            return "saved"

        assert save_data() == "saved"

    def test_blocks_execution_when_read_only(self):
        @require_write
        def save_data():
            return "saved"

        set_read_only(True)
        with pytest.raises(WriteBlockedError):
            save_data()

    def test_error_message_contains_function_name(self):
        @require_write
        def my_special_function():
            pass

        set_read_only(True)
        with pytest.raises(WriteBlockedError, match="my_special_function"):
            my_special_function()

    def test_error_message_contains_close_instruction(self):
        @require_write
        def save():
            pass

        set_read_only(True)
        with pytest.raises(WriteBlockedError, match="Close empathySync"):
            save()

    def test_preserves_function_metadata(self):
        @require_write
        def documented_func():
            """This is the docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is the docstring."


class TestCheckWritePermission:
    """Tests for the explicit check_write_permission() function."""

    def test_passes_when_writable(self):
        check_write_permission()  # Should not raise

    def test_raises_when_read_only(self):
        set_read_only(True)
        with pytest.raises(WriteBlockedError):
            check_write_permission()

    def test_error_message_mentions_read_only(self):
        set_read_only(True)
        with pytest.raises(WriteBlockedError, match="read-only mode"):
            check_write_permission()
