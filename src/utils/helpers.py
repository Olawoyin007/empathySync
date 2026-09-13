"""
Helper utilities for empathySync application
Supporting functions for logging, validation, and wellness features
"""

import logging
import os
from typing import List
from config.settings import settings


def setup_logging():
    """Setup application logging"""

    # Ensure logs directory exists
    settings.LOGS_DIR.mkdir(exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(settings.LOGS_DIR / settings.LOG_FILE),
            logging.StreamHandler(),  # Console output
        ],
    )

    # Log application start
    logger = logging.getLogger(__name__)
    logger.info(f"empathySync v{settings.APP_VERSION} starting in {settings.ENVIRONMENT} mode")


def validate_environment() -> List[str]:
    """Validate required environment configuration"""

    missing_config = settings.validate_config()

    if missing_config:
        logger = logging.getLogger(__name__)
        logger.warning(f"Missing configuration: {', '.join(missing_config)}")

    return missing_config


def format_wellness_tip(tip: str) -> str:
    """Format wellness tips with consistent styling"""
    return f" **Wellness Insight:** {tip}"


def create_progress_summary(conversation_count: int, days_active: int) -> str:
    """Create a simple progress summary for users"""

    if conversation_count == 0:
        return "Welcome to empathySync! This is the beginning of your AI wellness journey."

    avg_conversations = round(conversation_count / max(days_active, 1), 1)

    summary = f"You've had {conversation_count} reflective conversations "
    if days_active > 1:
        summary += f"over {days_active} days (avg {avg_conversations} per day). "
    else:
        summary += "today. "

    summary += "Thank you for prioritizing your digital wellness!"

    return summary


_APOSTROPHE_FOLD = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "′": "'"})


def normalize_for_matching(text: str) -> str:
    """
    Lowercase text and fold typographic apostrophes to the ASCII form.

    Trigger phrases are authored with a straight apostrophe ("don't want to
    be here"), but phone keyboards and word processors emit U+2019. Without
    this fold, a curly apostrophe silently drops a message off the crisis
    keyword floor. Applied to both sides of every substring match.
    """
    return text.lower().translate(_APOSTROPHE_FOLD)
