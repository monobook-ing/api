from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from app.services.resend import (
    send_invite_accepted_email,
    send_magic_link_email,
    send_welcome_email,
)


class ResendSkipEmailsTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(skip_emails=True)

    async def test_skip_magic_link_email_returns_early(self):
        with patch("app.services.resend.get_settings", return_value=self.settings), patch(
            "app.services.resend.httpx.AsyncClient"
        ) as mock_client:
            await send_magic_link_email(
                recipient="user@example.com", token="tkn", expires_at=datetime.now()
            )

        mock_client.assert_not_called()

    async def test_skip_welcome_email_returns_early(self):
        with patch("app.services.resend.get_settings", return_value=self.settings), patch(
            "app.services.resend.httpx.AsyncClient"
        ) as mock_client:
            await send_welcome_email(recipient="user@example.com")

        mock_client.assert_not_called()

    async def test_skip_invite_accepted_email_returns_early(self):
        with patch("app.services.resend.get_settings", return_value=self.settings), patch(
            "app.services.resend.httpx.AsyncClient"
        ) as mock_client:
            await send_invite_accepted_email(
                recipient="inviter@example.com",
                inviter_name="Inviter",
                invitee_name="Invitee",
                invitee_email="invitee@example.com",
                account_name="Account",
            )

        mock_client.assert_not_called()
