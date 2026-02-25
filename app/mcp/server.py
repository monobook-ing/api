from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from html import escape
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp
from supabase import Client

from app.agents.tools import check_availability, search_rooms, tool_create_booking
from app.api.deps import validate_property_id
from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.db.base import get_supabase_client
from app.mcp.auth import MCPHeaderAuthApp

settings = get_settings()

SEARCH_WIDGET_URI = "ui://widget/search-rooms.html"
AVAILABILITY_WIDGET_URI = "ui://widget/check-availability.html"
BOOKING_WIDGET_URI = "ui://widget/booking-confirmation.html"


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _security_schemes() -> list[dict[str, str]]:
    if settings.mcp_shared_secret:
        # ChatGPT Apps currently validates only `noauth` / `oauth` tagged schemes.
        # Keep MCP transport enforcement at the header middleware level when secret is set.
        return [{"type": "noauth"}]
    return [{"type": "noauth"}]


def _tool_meta(output_template: str, invoking: str, invoked: str) -> dict[str, Any]:
    return {
        "openai/outputTemplate": output_template,
        "openai/toolInvocation/invoking": invoking,
        "openai/toolInvocation/invoked": invoked,
        # Apps SDK compatibility: keep securitySchemes mirrored in _meta.
        "securitySchemes": _security_schemes(),
    }


def _resource_meta(widget_description: str) -> dict[str, Any]:
    mcp_origin = _origin(settings.mcp_public_base_url)
    widget_origin = _origin(settings.chatgpt_widget_base_url)

    connect_domains = [d for d in [mcp_origin] if d]
    # Allow script/CSS loading from both widget domain AND MCP origin (assets
    # are served from the API when CHATGPT_WIDGET_BASE_URL is not set separately).
    resource_domains = list({d for d in [widget_origin, mcp_origin] if d})

    meta: dict[str, Any] = {
        "openai/widgetDescription": widget_description,
        "openai/widgetPrefersBorder": True,
        "openai/widgetCSP": {
            "connect_domains": connect_domains,
            "resource_domains": resource_domains,
        },
    }
    if widget_origin:
        meta["openai/widgetDomain"] = widget_origin
    elif mcp_origin:
        meta["openai/widgetDomain"] = mcp_origin
    return meta


def _widget_assets() -> tuple[str | None, str | None]:
    """
    Return CSS/JS asset URLs for the ChatGPT widget runtime.

    - If `CHATGPT_WIDGET_BASE_URL` is set, load assets from that public base URL.
    - Falls back to `MCP_PUBLIC_BASE_URL` (assets are served from the same origin).
    - Otherwise, load from the same origin as the MCP server via relative paths.
    """
    base_url = settings.chatgpt_widget_base_url or settings.mcp_public_base_url
    if base_url:
        base = base_url.rstrip("/")
        return f"{base}/apps/chatgpt-widget.css", f"{base}/apps/chatgpt-widget.js"
    return "/apps/chatgpt-widget.css", "/apps/chatgpt-widget.js"


def _render_widget_html(widget: str) -> str:
    css_url, script_url = _widget_assets()
    bootstrap = escape(json.dumps({"widget": widget}))
    if script_url is None:
        return (
            "<!doctype html><html><head><meta charset='utf-8'></head><body>"
            "<div style='font-family: sans-serif; padding: 12px;'>"
            "Widget runtime is not configured. Set CHATGPT_WIDGET_BASE_URL to enable rendering."
            "</div></body></html>"
        )

    css_tag = f"<link rel='stylesheet' href='{escape(css_url)}' />" if css_url else ""
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width, initial-scale=1' />"
        f"{css_tag}"
        "</head>"
        "<body>"
        "<div id='monobook-widget-root'></div>"
        f"<script id='monobook-widget-bootstrap' type='application/json'>{bootstrap}</script>"
        f"<script type='module' src='{escape(script_url)}'></script>"
        "</body>"
        "</html>"
    )


def _tool_result(text: str, structured_content: dict[str, Any], widget: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured_content,
        "_meta": {"monobook/widget": widget},
    }


def _tool_error(message: str, widget: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"error": message},
        "isError": True,
        "_meta": {"monobook/widget": widget},
    }


def _session_id(ctx: Context | None) -> str | None:
    if not ctx:
        return None
    try:
        if ctx.request_id is None:
            return None
        return str(ctx.request_id)
    except Exception:
        return None


async def _get_openai_api_key(client: Client, property_id: str) -> str:
    key = await get_decrypted_api_key(client, property_id, "openai")
    if key:
        return key
    if settings.openai_api_key:
        return settings.openai_api_key
    raise ValueError("OpenAI API key is not configured for this property.")


mcp_server = FastMCP(
    name="Monobooking MCP Server",
    instructions=(
        "Tools for hotel room search, availability checks, and booking creation. "
        "Always pass a valid UUID property_id and ISO dates."
    ),
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


@mcp_server.tool(
    name="search_rooms",
    description="Search available rooms for a property and optional date/guest constraints.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=SEARCH_WIDGET_URI,
        invoking="Searching rooms...",
        invoked="Room results ready.",
    ),
    structured_output=True,
)
async def mcp_search_rooms(
    property_id: str,
    query: str,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)
    try:
        api_key = await _get_openai_api_key(client, property_id)
    except ValueError as exc:
        return _tool_error(str(exc), "search_rooms")

    result = await search_rooms(
        client=client,
        property_id=property_id,
        api_key=api_key,
        query=query,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        session_id=session_id,
        source="chatgpt",
    )
    count = result.get("count", 0)
    return _tool_result(
        text=f"Found {count} room(s).",
        structured_content=result,
        widget="search_rooms",
    )


@mcp_server.tool(
    name="check_availability",
    description="Check whether a room is available for specific check-in and check-out dates.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=AVAILABILITY_WIDGET_URI,
        invoking="Checking availability...",
        invoked="Availability check complete.",
    ),
    structured_output=True,
)
async def mcp_check_availability(
    property_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    result = await check_availability(
        client=client,
        property_id=property_id,
        room_id=room_id,
        check_in=check_in,
        check_out=check_out,
        session_id=session_id,
        source="chatgpt",
    )

    room_response = (
        client.table("rooms")
        .select("id, property_id, name, type, description, price_per_night, max_guests, amenities, images")
        .eq("id", room_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    if room_response.data:
        room = room_response.data
        result["room"] = {
            "id": room["id"],
            "property_id": room["property_id"],
            "name": room["name"],
            "type": room["type"],
            "description": room.get("description", ""),
            "price_per_night": str(room["price_per_night"]),
            "max_guests": room.get("max_guests"),
            "amenities": room.get("amenities", []),
            "images": room.get("images", []),
        }

    status_text = "available" if result.get("available") else "unavailable"
    return _tool_result(
        text=f"Room {room_id} is {status_text} for {check_in} to {check_out}.",
        structured_content=result,
        widget="check_availability",
    )


@mcp_server.tool(
    name="create_booking",
    description="Create a confirmed booking for a room and guest details.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=BOOKING_WIDGET_URI,
        invoking="Creating booking...",
        invoked="Booking created.",
    ),
    structured_output=True,
)
async def mcp_create_booking(
    property_id: str,
    room_id: str,
    guest_name: str,
    check_in: str,
    check_out: str,
    guest_email: str | None = None,
    guests: int = 2,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    result = await tool_create_booking(
        client=client,
        property_id=property_id,
        room_id=room_id,
        guest_name=guest_name,
        guest_email=guest_email,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        session_id=session_id,
        source="chatgpt",
        booking_status="confirmed",
    )

    if "error" in result:
        return _tool_error(str(result["error"]), "create_booking")

    return _tool_result(
        text=result.get("message", "Booking created successfully."),
        structured_content=result,
        widget="create_booking",
    )


@mcp_server.resource(
    SEARCH_WIDGET_URI,
    name="Monobook Search Rooms Widget",
    description="Interactive room carousel and booking flow for search results.",
    mime_type="text/html",
    meta=_resource_meta(
        "Browse room cards, configure dates and guests, and complete booking steps."
    ),
)
def mcp_search_rooms_widget() -> str:
    return _render_widget_html("search_rooms")


@mcp_server.resource(
    AVAILABILITY_WIDGET_URI,
    name="Monobook Availability Widget",
    description="Availability summary widget for selected room and dates.",
    mime_type="text/html",
    meta=_resource_meta(
        "Shows room availability result and enables next booking action."
    ),
)
def mcp_availability_widget() -> str:
    return _render_widget_html("check_availability")


@mcp_server.resource(
    BOOKING_WIDGET_URI,
    name="Monobook Booking Confirmation Widget",
    description="Booking confirmation and payment summary widget.",
    mime_type="text/html",
    meta=_resource_meta(
        "Displays booking totals and confirmation details after successful booking."
    ),
)
def mcp_booking_widget() -> str:
    return _render_widget_html("create_booking")


_mcp_asgi_app: MCPHeaderAuthApp | None = None
_mcp_lifespan: AbstractAsyncContextManager[None] | None = None


def get_mcp_asgi_app() -> ASGIApp:
    global _mcp_asgi_app
    if _mcp_asgi_app is None:
        _mcp_asgi_app = MCPHeaderAuthApp(
            mcp_server.streamable_http_app(),
            shared_secret=settings.mcp_shared_secret,
        )
    return _mcp_asgi_app


async def startup_mcp() -> None:
    """Start the MCP session manager lifecycle within the parent FastAPI app."""
    global _mcp_lifespan
    if _mcp_lifespan is not None:
        return

    get_mcp_asgi_app()
    _mcp_lifespan = mcp_server.session_manager.run()
    await _mcp_lifespan.__aenter__()


async def shutdown_mcp() -> None:
    """Stop the MCP session manager lifecycle."""
    global _mcp_lifespan, _mcp_asgi_app
    if _mcp_lifespan is None:
        return

    await _mcp_lifespan.__aexit__(None, None, None)
    _mcp_lifespan = None

    # StreamableHTTPSessionManager instances are single-use; rebuild for next startup.
    mcp_server._session_manager = None  # type: ignore[attr-defined]
    if _mcp_asgi_app is not None:
        _mcp_asgi_app.app = mcp_server.streamable_http_app()
