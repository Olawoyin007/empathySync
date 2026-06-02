"""Tests for CLI mode."""

import logging
from unittest.mock import patch, MagicMock


class TestCLIArguments:
    def test_list_domains_flag_calls_list_domains(self):
        with patch("src.cli.list_domains") as mock_list_domains:
            with patch("sys.argv", ["empathysync", "--list-domains"]):
                from src.cli import main

                main()
            assert mock_list_domains.called

    def test_mode_cli_calls_run_cli(self):
        with patch("src.cli.run_cli") as mock_run_cli:
            with patch("sys.argv", ["empathysync", "--mode", "cli"]):
                from src.cli import main

                main()
            assert mock_run_cli.called

    def test_mode_web_calls_run_streamlit(self):
        with patch("src.cli.run_streamlit") as mock_run_streamlit:
            with patch("sys.argv", ["empathysync", "--mode", "web"]):
                from src.cli import main

                main()
            assert mock_run_streamlit.called

    def test_default_mode_calls_run_streamlit(self):
        with patch("src.cli.run_streamlit") as mock_run_streamlit:
            with patch("sys.argv", ["empathysync"]):
                from src.cli import main

                main()
            assert mock_run_streamlit.called

    def test_log_level_debug_sets_root_logger(self):
        """--log-level DEBUG overrides the root logger level."""
        root = logging.getLogger()
        original = root.level
        try:
            with patch("src.cli.run_streamlit"):
                with patch("sys.argv", ["empathysync", "--log-level", "DEBUG"]):
                    from src.cli import main

                    main()
            assert root.level == logging.DEBUG
        finally:
            root.setLevel(original)

    def test_log_level_warning_sets_root_logger(self):
        """--log-level WARNING overrides the root logger level."""
        root = logging.getLogger()
        original = root.level
        try:
            with patch("src.cli.run_streamlit"):
                with patch("sys.argv", ["empathysync", "--log-level", "WARNING"]):
                    from src.cli import main

                    main()
            assert root.level == logging.WARNING
        finally:
            root.setLevel(original)

    def test_log_level_absent_does_not_modify_root_logger(self):
        """When --log-level is omitted, root logger level is left untouched."""
        root = logging.getLogger()
        root.setLevel(logging.ERROR)
        try:
            with patch("src.cli.run_streamlit"):
                with patch("sys.argv", ["empathysync"]):
                    from src.cli import main

                    main()
            assert root.level == logging.ERROR
        finally:
            root.setLevel(logging.WARNING)

    def test_log_level_invalid_choice_exits_nonzero(self):
        """An unrecognised --log-level value causes argparse to exit non-zero."""
        import pytest

        with patch("sys.argv", ["empathysync", "--log-level", "VERBOSE"]):
            from src.cli import main

            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0


class TestListDomains:
    def test_list_domains_prints_all_domains(self, capsys):
        """Test that list_domains prints all 8 domains with their risk weights."""
        from src.cli import list_domains

        list_domains()

        output = capsys.readouterr().out

        # Check that all 8 domains are present
        assert "crisis" in output
        assert "harmful" in output
        assert "health" in output
        assert "money" in output
        assert "emotional" in output
        assert "relationships" in output
        assert "spirituality" in output
        assert "logistics" in output

        # Check that risk weights are present
        assert "risk weight:" in output

        # Check that descriptions are present
        assert "Suicidal ideation" in output or "Illegal activities" in output

    def test_list_domains_sorted_by_risk_weight(self, capsys):
        """Test that domains are sorted by risk weight in descending order."""
        from src.cli import list_domains

        list_domains()

        output = capsys.readouterr().out
        lines = output.strip().split("\n")

        # Find the domain lines (skip the header)
        domain_lines = [line for line in lines if "risk weight:" in line]

        # Extract risk weights from each line
        import re

        weights = []
        for line in domain_lines:
            match = re.search(r"risk weight:\s*([\d.]+)", line)
            if match:
                weights.append(float(match.group(1)))

        # Verify that weights are in descending order
        assert weights == sorted(weights, reverse=True)


class TestRunCLI:
    def test_run_cli_invokes_adapter(self):
        """Test that run_cli actually wires up and calls adapter.run()."""
        mock_adapter_instance = MagicMock()

        with (
            patch("models.ai_wellness_guide.WellnessGuide"),
            patch("models.conversation_session.ConversationSession"),
            patch("utils.wellness_tracker.WellnessTracker"),
            patch("utils.trusted_network.TrustedNetwork"),
            patch("interfaces.cli_adapter.CLIAdapter") as mock_adapter,
        ):

            mock_adapter.return_value = mock_adapter_instance

            with patch("sys.argv", ["empathysync", "--mode", "cli"]):
                from src.cli import main

                main()

            mock_adapter_instance.run.assert_called_once()
