"""
Helper utilities for empathySync application
Supporting functions for logging, validation, and wellness features
"""

import logging
import os
import re
from typing import List, Optional, Tuple
from urllib.parse import quote
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


# A phone number once the cosmetic characters are stripped: an optional leading
# "+", then 7 to 15 digits (E.164 caps at 15; 7 is the shortest real number).
_PHONE_SHAPE = re.compile(r"^\+?\d{7,15}$")
_PHONE_NOISE = re.compile(r"[\s().\-/]")

# Deliberately loose. This decides which app to open, not whether an address is
# deliverable - the user typed it and the mail client will tell them if it is
# wrong. Rejecting a valid-but-unusual address would be the worse failure.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_handoff_links(contact: str, message: str) -> List[Tuple[str, str]]:
    """Turn a stored contact into links that open the user's own apps.

    Returns ``[(kind, url), ...]`` where kind is ``"email"``, ``"sms"`` or
    ``"tel"``, most-useful first. Empty when the contact is not something an
    operating system can act on - "the pub on Thursdays" is a perfectly good
    thing to have saved, and gets the copy button instead.

    A phone number yields both: ``sms:`` carries the drafted message, ``tel:``
    cannot and is offered second for people who would rather just call.

    This is a handoff, not an integration, and the distinction is the whole
    point: these schemes are handled by the OS, so the app never sees the
    recipient, the send, or the reply. Sending mail properly would mean an
    SMTP server or an API key, and "all processing must remain local"
    forecloses that.
    """
    contact = (contact or "").strip()
    if not contact:
        return []

    body = quote(message or "", safe="")

    if _EMAIL_SHAPE.match(contact):
        return [("email", f"mailto:{quote(contact, safe='@')}?body={body}")]

    number = _PHONE_NOISE.sub("", contact)
    if _PHONE_SHAPE.match(number):
        number = quote(number, safe="+")
        # "?body=" is the form Android and current iOS both accept.
        return [("sms", f"sms:{number}?body={body}"), ("tel", f"tel:{number}")]

    return []
