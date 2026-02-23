from __future__ import annotations

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MCP_AUTH_HEADER = "x-monobook-mcp-key"


class MCPHeaderAuthApp:
    """ASGI wrapper that protects the mounted MCP app with a shared secret header."""

    def __init__(self, app: ASGIApp, shared_secret: str | None):
        self.app = app
        self.shared_secret = (shared_secret or "").strip()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # If no shared secret is configured, MCP runs in "No Auth" mode.
        if not self.shared_secret:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        provided = headers.get(MCP_AUTH_HEADER, "")
        authorized = secrets.compare_digest(provided, self.shared_secret)

        if not authorized:
            response = JSONResponse(
                {"detail": "Unauthorized MCP request."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
