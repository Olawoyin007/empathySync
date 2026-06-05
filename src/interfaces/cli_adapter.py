"""
CLIAdapter - Terminal interface for empathySync.

Proof-of-concept adapter demonstrating that the ConversationSession
can be driven by any interface, not just Streamlit.

Usage:
    empathysync --mode cli
"""

import sys
from typing import Dict, List

from config.settings import settings
from models.conversation_result import ConversationResult
from models.conversation_session import ConversationSession


class CLIAdapter:
    """Simple terminal interface for empathySync conversations."""

    def __init__(self, session: ConversationSession):
        self.session = session

    def render_result(self, result: ConversationResult) -> None:
        """Print conversation result to terminal."""
        if result.is_cooldown_active:
            print(f"\n[Cooldown] {result.cooldown_message}")
            if result.suggested_handoff_person:
                print(f"Consider reaching out to {result.suggested_handoff_person}.")
            return

        if result.response:
            print(f"\n{result.response}")

        # Show risk info in debug mode
        if result.risk_assessment:
            domain = result.risk_assessment.get("domain", "unknown")
            risk = result.risk_assessment.get("risk_weight", 0)
            method = result.risk_assessment.get("classification_method", "keyword")
            print(f"\n  [{domain} | risk: {risk:.1f} | {method}]")

        if result.policy_action:
            policy_type = result.policy_action.get("type", "")
            print(f"  [Policy: {policy_type}]")

        # Handle pending interactions
        if result.pending_shift and not self.session.acknowledged_shift:
            accept = self.prompt_intent_shift(result.pending_shift)
            self.session.acknowledge_intent_shift(accept)

        if result.pending_graduation:
            action = self.prompt_graduation(
                result.pending_graduation["category"],
                result.pending_graduation["prompt"],
            )
            if action == "accept":
                self.session.accept_graduation()
            else:
                self.session.dismiss_graduation()

    def render_stream(self, result: ConversationResult) -> None:
        """Stream tokens to terminal as they arrive."""
        if result.is_cooldown_active:
            print(f"\n[Cooldown] {result.cooldown_message}")
            if result.suggested_handoff_person:
                print(f"Consider reaching out to {result.suggested_handoff_person}.")
            return

        if result.response_stream:
            sys.stdout.write("\n")
            for token in result.response_stream:
                sys.stdout.write(token)
                sys.stdout.flush()
            sys.stdout.write("\n")

            # Finalize stream to populate metadata
            final = self.session.finalize_stream()

            # Show risk info in debug mode
            if final.risk_assessment:
                domain = final.risk_assessment.get("domain", "unknown")
                risk = final.risk_assessment.get("risk_weight", 0)
                method = final.risk_assessment.get("classification_method", "keyword")
                print(f"\n  [{domain} | risk: {risk:.1f} | {method}]")

            if final.policy_action:
                policy_type = final.policy_action.get("type", "")
                print(f"  [Policy: {policy_type}]")

            # Handle pending interactions
            if final.pending_shift and not self.session.acknowledged_shift:
                accept = self.prompt_intent_shift(final.pending_shift)
                self.session.acknowledge_intent_shift(accept)

            if final.pending_graduation:
                action = self.prompt_graduation(
                    final.pending_graduation["category"],
                    final.pending_graduation["prompt"],
                )
                if action == "accept":
                    self.session.accept_graduation()
                else:
                    self.session.dismiss_graduation()
        elif result.response:
            # Non-streaming fallback (early returns like cooldown, crisis)
            print(f"\n{result.response}")

    def prompt_intent_shift(self, shift_info: Dict) -> bool:
        """Prompt user about intent shift via terminal."""
        print("\n---")
        print(
            "It sounds like this became about more than just the task. "
            "Want to pause and talk about what's coming up?"
        )
        print("  1. Let's talk about what's coming up")
        print("  2. Just help with the task")
        try:
            choice = input("Choose (1 or 2): ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        return choice == "1"

    def prompt_graduation(self, category: str, prompt_text: str) -> str:
        """Prompt user about graduation via terminal."""
        print(f"\n---\n{prompt_text}")
        print("  1. Show me some tips")
        print("  2. Just help me")
        try:
            choice = input("Choose (1 or 2): ").strip()
        except (EOFError, KeyboardInterrupt):
            return "dismiss"
        return "accept" if choice == "1" else "dismiss"

    def run(self) -> None:
        """Main conversation loop."""
        print("empathySync — Help that knows when to stop")
        engine = settings.OLLAMA_MODEL or "(not set)"
        if settings.OLLAMA_CLASSIFIER_MODEL:
            classifier = f"{settings.OLLAMA_CLASSIFIER_MODEL} (dedicated)"
        else:
            classifier = f"{engine} (shared)"
        print(f"Engine: {engine}  |  Classifier: {classifier}")
        print("Type 'exit' to quit, 'summary' for session summary\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("\nGoodbye.")
                break

            if user_input.lower() == "summary":
                summary = self.session.get_session_summary()
                print(f"\nTurns: {summary.get('turn_count', 0)}")
                print(f"Domains: {', '.join(summary.get('domains_touched', []))}")
                print(f"Max risk: {summary.get('max_risk_weight', 0):.1f}")
                continue

            result = self.session.process_message_stream(user_input)
            if result.is_streaming:
                self.render_stream(result)
            else:
                self.render_result(result)
