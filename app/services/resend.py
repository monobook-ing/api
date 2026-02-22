from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings

RESEND_EMAILS_URL = "https://api.resend.com/emails"


class ResendError(Exception):
    """Base exception for Resend adapter errors."""


class ResendConfigurationError(ResendError):
    """Raised when required Resend configuration is missing."""


class ResendSendError(ResendError):
    """Raised when the Resend API responds with an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _build_magic_link(token: str, email: str, base_url: str | None) -> str:
    if not base_url:
        return token

    if "{token}" in base_url:
        magic_link = base_url.format(token=token)
        separator = "&" if "?" in magic_link else "?"
        return f"{magic_link}{separator}email={quote(email)}"

    # Strip any trailing ?token= or &token= to avoid duplication
    if base_url.endswith("?token=") or base_url.endswith("&token="):
        base_url = base_url[:-7]  # Remove the last 7 characters (?token= or &token=)

    base_url = base_url.rstrip('/')
    separator = "&" if "?" in base_url else "?"

    # Build URL with both token and email parameters
    encoded_email = quote(email)
    return f"{base_url}{separator}token={token}&email={encoded_email}"


async def send_magic_link_email(*, recipient: str, token: str, expires_at: datetime) -> None:
    settings = get_settings()

    if settings.skip_emails:
        return

    if not settings.resend_api_key:
        raise ResendConfigurationError("RESEND_API_KEY is not configured.")

    if not settings.resend_from_email:
        raise ResendConfigurationError("RESEND_FROM_EMAIL is not configured.")

    magic_link = _build_magic_link(token, recipient, settings.magic_link_base_url)
    subject = f"Your sign-in link for {settings.app_name}"

    text_body = "\n".join(
        [
            f"Use the magic link below to sign in to {settings.app_name}:",
            magic_link,
            "",
            f"This link expires at {expires_at.isoformat()}.",
            "",
            "If you did not request this email, you can safely ignore it.",
        ]
    )

    html_body = (
        f"<p>Use the magic link below to sign in to {settings.app_name}:</p>"
        f'<p><a href="{magic_link}">{magic_link}</a></p>'
        f"<p>This link expires at {expires_at.isoformat()}.</p>"
        "<p>If you did not request this email, you can safely ignore it.</p>"
    )

    payload: dict[str, Any] = {
        "from": str(settings.resend_from_email),
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(RESEND_EMAILS_URL, json=payload, headers=headers)

    if not response.is_success:
        error_message = "Resend email send failed."

        try:
            data = response.json()
            if isinstance(data, dict) and data.get("message"):
                error_message = str(data["message"])
        except ValueError:
            pass

        raise ResendSendError(error_message, status_code=response.status_code)


async def send_welcome_email(*, recipient: str, first_name: str | None = None) -> None:
    """Send a welcome email to a new user."""
    settings = get_settings()

    if settings.skip_emails:
        return

    if not settings.resend_api_key:
        raise ResendConfigurationError("RESEND_API_KEY is not configured.")

    if not settings.resend_from_email:
        raise ResendConfigurationError("RESEND_FROM_EMAIL is not configured.")

    greeting_name = first_name or recipient.split("@")[0]
    subject = f"Welcome to {settings.app_name}!"

    text_body = "\n".join(
        [
            f"Hi {greeting_name},",
            "",
            f"Welcome to {settings.app_name}! We're excited to have you on board.",
            "You can sign in anytime using your email and magic link.",
            "",
            "If you have any questions, just reply to this email.",
        ]
    )

    html_body = (
        f"<p>Hi {greeting_name},</p>"
        f"<p>Welcome to <strong>{settings.app_name}</strong>! "
        "We're excited to have you on board.</p>"
        "<p>You can sign in anytime using your email and magic link.</p>"
        "<p>If you have any questions, just reply to this email.</p>"
    )

    payload: dict[str, Any] = {
        "from": str(settings.resend_from_email),
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(RESEND_EMAILS_URL, json=payload, headers=headers)

    if not response.is_success:
        error_message = "Resend email send failed."

        try:
            data = response.json()
            if isinstance(data, dict) and data.get("message"):
                error_message = str(data["message"])
        except ValueError:
            pass

        raise ResendSendError(error_message, status_code=response.status_code)


async def send_invite_accepted_email(
    *,
    recipient: str,
    inviter_name: str | None,
    invitee_name: str | None,
    invitee_email: str,
    account_name: str | None,
) -> None:
    """Notify an inviter that their invitation was accepted."""
    settings = get_settings()

    if settings.skip_emails:
        return

    if not settings.resend_api_key:
        raise ResendConfigurationError("RESEND_API_KEY is not configured.")

    if not settings.resend_from_email:
        raise ResendConfigurationError("RESEND_FROM_EMAIL is not configured.")

    inviter_display = inviter_name or recipient.split("@")[0]
    invitee_display = invitee_name or invitee_email.split("@")[0]
    account_display = account_name or "the account"

    subject = f"{invitee_display} accepted your invitation to {settings.app_name}"

    text_body = "\n".join(
        [
            f"Hi {inviter_display},",
            "",
            (
                f"{invitee_display} ({invitee_email}) accepted your invitation "
                f"to join {account_display}"
            ),
            f"on {settings.app_name}.",
            "",
            "They now have access to the account. No further action is needed.",
        ]
    )

    html_body = (
        f"<p>Hi {inviter_display},</p>"
        f"<p><strong>{invitee_display}</strong> ({invitee_email}) accepted your invitation "
        f"to join <strong>{account_display}</strong> on {settings.app_name}.</p>"
        "<p>They now have access to the account. No further action is needed.</p>"
    )

    payload: dict[str, Any] = {
        "from": str(settings.resend_from_email),
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(RESEND_EMAILS_URL, json=payload, headers=headers)

    if not response.is_success:
        error_message = "Resend email send failed."

        try:
            data = response.json()
            if isinstance(data, dict) and data.get("message"):
                error_message = str(data["message"])
        except ValueError:
            pass

        raise ResendSendError(error_message, status_code=response.status_code)
