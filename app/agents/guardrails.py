from __future__ import annotations

import re
from datetime import date, timedelta


def validate_dates(check_in: str, check_out: str) -> str | None:
    """Validate booking dates. Returns error message or None if valid."""
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
    except (ValueError, TypeError):
        return "Invalid date format. Use YYYY-MM-DD."

    today = date.today()
    if ci < today:
        return "Check-in date cannot be in the past."
    if co <= ci:
        return "Check-out must be after check-in."
    if (co - ci).days > 30:
        return "Maximum stay is 30 nights."
    if ci > today + timedelta(days=365):
        return "Cannot book more than 1 year in advance."
    return None


def validate_guests(count: int) -> str | None:
    """Validate guest count. Returns error message or None if valid."""
    if not isinstance(count, int) or count < 1:
        return "Guest count must be at least 1."
    if count > 20:
        return "Maximum 20 guests per booking."
    return None


def sanitize_input(text: str) -> str:
    """Strip potential prompt injection patterns from user input."""
    # Remove common injection patterns
    patterns = [
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        r"(?i)you\s+are\s+now\s+a",
        r"(?i)system\s*:\s*",
        r"(?i)assistant\s*:\s*",
        r"(?i)<\|.*?\|>",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip()
