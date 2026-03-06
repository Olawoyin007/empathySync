"""Tests for CLI mode."""
from unittest.mock import patch, MagicMock


class TestCLIArguments:
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


class TestRunCLI:
    def test_run_cli_invokes_adapter(self):
        """Test that run_cli actually wires up and calls adapter.run()."""
        mock_adapter_instance = MagicMock()

        with patch("models.ai_wellness_guide.WellnessGuide"), \
            patch("models.conversation_session.ConversationSession"), \
            patch("utils.wellness_tracker.WellnessTracker"), \
            patch("utils.trusted_network.TrustedNetwork"), \
            patch("interfaces.cli_adapter.CLIAdapter") as mock_adapter:

            mock_adapter.return_value = mock_adapter_instance

            with patch("sys.argv", ["empathysync", "--mode", "cli"]):
                from src.cli import main
                main()

            mock_adapter_instance.run.assert_called_once()