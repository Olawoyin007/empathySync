"""
CLI entry point for empathySync.

Usage:
    empathysync              # Launches Streamlit web interface (default)
    empathysync --mode web   # Same as above
    empathysync --mode cli   # Direct terminal interface (no browser needed)
    empathysync --maintenance  # Run maintenance tasks and exit
    empathysync --version    # Print version and exit
"""

import sys
import argparse
import logging
import subprocess
from pathlib import Path


def run_streamlit():
    """Launch empathySync Streamlit app."""
    app_path = Path(__file__).parent / "app.py"
    sys.exit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app_path),
                "--server.headless",
                "true",
            ]
        )
    )


def run_cli():
    """Launch empathySync in direct terminal mode."""
    # Add src to path for imports (same as app.py)
    sys.path.append(str(Path(__file__).parent))

    from models.ai_wellness_guide import WellnessGuide
    from models.conversation_session import ConversationSession
    from utils.wellness_tracker import WellnessTracker
    from utils.trusted_network import TrustedNetwork
    from interfaces.cli_adapter import CLIAdapter

    guide = WellnessGuide()
    tracker = WellnessTracker()
    network = TrustedNetwork()

    session = ConversationSession(guide, tracker, network)
    adapter = CLIAdapter(session)
    adapter.run()


def list_domains():
    """Print supported domains and their risk weights, then exit."""
    sys.path.append(str(Path(__file__).parent))

    from utils.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()
    domains = loader.get_all_domains()

    print("Supported domains:")
    # Sort by risk weight (descending) for better readability
    sorted_domains = sorted(domains.items(), key=lambda x: x[1].get("risk_weight", 0), reverse=True)

    for domain_name, config in sorted_domains:
        risk_weight = config.get("risk_weight", 0)
        description = config.get("description", "")
        # Format: domain (padded to 14 chars) risk weight (padded to 14 chars) - description
        print(f"  {domain_name:<14} risk weight: {risk_weight:<5} - {description}")


def run_maintenance():
    """Run maintenance tasks: prune old data, validate integrity, print summary."""
    sys.path.append(str(Path(__file__).parent))

    from config.settings import settings
    from utils.storage_backend import get_storage_backend
    from utils.wellness_tracker import WellnessTracker

    print("empathySync maintenance")
    print("=" * 40)

    # 1. Data pruning
    retention = settings.DATA_RETENTION_DAYS
    if retention > 0:
        print(f"\nPruning records older than {retention} days...")
        try:
            backend = get_storage_backend()
            pruned = backend.prune_old_data(retention)
            if pruned > 0:
                print(f"  Removed {pruned} old records")
            else:
                print("  No records to prune")
        except Exception as e:
            print(f"  Pruning failed: {e}")
    else:
        print("\nData pruning disabled (DATA_RETENTION_DAYS=0)")

    # 2. Dependency score check
    print("\nChecking dependency patterns...")
    try:
        tracker = WellnessTracker()
        signals = tracker.calculate_dependency_signals()
        score = signals.get("dependency_score", 0)
        sessions_week = signals.get("sessions_week", 0)
        print(f"  Sessions this week: {sessions_week}")
        print(f"  Dependency score: {score:.1f}/10")
        if score >= 6:
            print("  Warning: elevated dependency pattern detected")
        elif score <= 2:
            print("  Healthy usage pattern")
    except Exception as e:
        print(f"  Dependency check failed: {e}")

    # 3. Data integrity
    print("\nValidating data integrity...")
    try:
        backend = get_storage_backend()
        # Quick read test - if data is corrupt, this will raise
        backend.get_recent_check_ins(days=1)
        backend.get_recent_policy_events(limit=1)
        print("  Data files OK")
    except Exception as e:
        print(f"  Data integrity issue: {e}")

    # 4. Configuration summary
    print("\nConfiguration:")
    print(f"  Model: {settings.OLLAMA_MODEL or '(not set)'}")
    print(f"  Host: {settings.OLLAMA_HOST or '(not set)'}")
    print(f"  Storage: {'SQLite' if settings.USE_SQLITE else 'JSON'}")
    print(f"  Retention: {retention} days" if retention > 0 else "  Retention: disabled")

    print("\n" + "=" * 40)
    print("Maintenance complete")


def main():
    """Main entry point with mode selection."""
    sys.path.append(str(Path(__file__).parent))
    from config.settings import settings

    parser = argparse.ArgumentParser(description="empathySync - Help that knows when to stop")
    parser.add_argument(
        "--mode",
        choices=["web", "cli"],
        default="web",
        help="Interface mode: web (Streamlit) or cli (terminal)",
    )
    parser.add_argument(
        "--list-domains",
        action="store_true",
        help="Print supported domains and their risk weights, then exit",
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        help="Run maintenance tasks (prune data, check integrity) and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{settings.APP_NAME} v{settings.APP_VERSION}",
        help="Show the application version and exit",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Set log verbosity (overrides LOG_LEVEL env var)",
    )

    args = parser.parse_args()

    if args.log_level:
        logging.getLogger().setLevel(args.log_level)

    if args.list_domains:
        list_domains()
    elif args.maintenance:
        run_maintenance()
    elif args.mode == "cli":
        run_cli()
    else:
        run_streamlit()


if __name__ == "__main__":
    main()
