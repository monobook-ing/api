from __future__ import annotations

import json
import logging
from contextlib import AbstractAsyncContextManager
from html import escape
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp
from supabase import Client

from app.agents.tools import (
    check_availability,
    search_hotels,
    search_rooms,
    tool_create_booking,
)
from app.api.deps import validate_property_id
from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.db.base import get_supabase_client
from app.mcp.auth import MCPHeaderAuthApp

settings = get_settings()

SEARCH_WIDGET_URI = "ui://widget/search-rooms.html"
HOTELS_WIDGET_URI = "ui://widget/search-hotels.html"
AVAILABILITY_WIDGET_URI = "ui://widget/check-availability.html"
BOOKING_WIDGET_URI = "ui://widget/booking-confirmation.html"

logger = logging.getLogger(__name__)

_cached_widget_js: str | None = None
_cached_widget_css: str | None = None


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _ordered_unique(values: list[str | None]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


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
    css_url, script_url = _widget_assets()
    css_origin = _origin(css_url)
    script_origin = _origin(script_url)

    connect_domains = [d for d in [mcp_origin] if d]
    # Allow script/CSS loading from configured widget domain, MCP origin, and
    # explicit asset origins when split-domain hosting is used.
    resource_domains = _ordered_unique(
        [widget_origin, mcp_origin, css_origin, script_origin]
    )

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

    - If explicit `CHATGPT_WIDGET_JS_URL` + `CHATGPT_WIDGET_CSS_URL` are set,
      use those URLs as-is.
    - Else if `CHATGPT_WIDGET_BASE_URL` is set, load assets from that public
      base URL (`/apps/chatgpt-widget.{js,css}`).
    - Falls back to `MCP_PUBLIC_BASE_URL` in legacy mode.
    - Otherwise, load from the same origin as the MCP server via relative paths.
    """
    if settings.chatgpt_widget_js_url or settings.chatgpt_widget_css_url:
        if not (settings.chatgpt_widget_js_url and settings.chatgpt_widget_css_url):
            raise ValueError(
                "CHATGPT_WIDGET_JS_URL and CHATGPT_WIDGET_CSS_URL must be set together."
            )
        return settings.chatgpt_widget_css_url, settings.chatgpt_widget_js_url

    base_url = settings.chatgpt_widget_base_url or settings.mcp_public_base_url
    if base_url:
        base = base_url.rstrip("/")
        return f"{base}/apps/chatgpt-widget.css", f"{base}/apps/chatgpt-widget.js"
    return "/apps/chatgpt-widget.css", "/apps/chatgpt-widget.js"


def get_widget_asset_urls() -> tuple[str | None, str | None]:
    """Resolve widget CSS/JS asset URLs based on runtime configuration."""
    return _widget_assets()


def _inline_tag_safe(content: str, tag: str) -> str:
    closing = f"</{tag}"
    return content.replace(closing, f"<\\/{tag}")


async def _refresh_widget_asset_cache() -> None:
    global _cached_widget_js, _cached_widget_css

    css_url, script_url = _widget_assets()
    if not css_url or not script_url:
        _cached_widget_css = None
        _cached_widget_js = None
        return

    if not (
        css_url.startswith(("http://", "https://"))
        and script_url.startswith(("http://", "https://"))
    ):
        _cached_widget_css = None
        _cached_widget_js = None
        logger.info(
            "Skipping widget asset prefetch: expected absolute HTTP(S) URLs, got css=%s js=%s",
            css_url,
            script_url,
        )
        return

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            css_response = await client.get(css_url, follow_redirects=True)
            css_response.raise_for_status()

            js_response = await client.get(script_url, follow_redirects=True)
            js_response.raise_for_status()

        _cached_widget_css = css_response.text
        _cached_widget_js = js_response.text
        logger.info(
            "Loaded widget assets into inline cache (css=%d bytes, js=%d bytes).",
            len(_cached_widget_css),
            len(_cached_widget_js),
        )
    except Exception as exc:
        _cached_widget_css = None
        _cached_widget_js = None
        logger.warning(
            "Failed to prefetch widget assets for inlining; "
            "falling back to external references. css=%s js=%s error=%s",
            css_url,
            script_url,
            exc,
        )


def _render_widget_html(widget: str) -> str:
    css_url, script_url = _widget_assets()
    bootstrap = escape(json.dumps({"widget": widget}))
    if script_url is None:
        return (
            "<!doctype html><html><head><meta charset='utf-8'></head><body>"
            "<div style='font-family: sans-serif; padding: 12px;'>"
            "Widget runtime is not configured. Set widget asset URLs to enable rendering."
            "</div></body></html>"
        )

    if _cached_widget_js is not None and _cached_widget_css is not None:
        css_tag = f"<style>{_inline_tag_safe(_cached_widget_css, 'style')}</style>"
        script_tag = f"<script>{_inline_tag_safe(_cached_widget_js, 'script')}</script>"
    else:
        css_tag = f"<link rel='stylesheet' href='{escape(css_url)}' />" if css_url else ""
        script_tag = f"<script type='module' src='{escape(script_url)}'></script>"

    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width, initial-scale=1' />"
        f"{css_tag}"
        "</head>"
        "<body>"
        "<div id='monobook-widget-root'>"
        "<div style='font-family: Inter, -apple-system, BlinkMacSystemFont, "
        "Segoe UI, sans-serif; padding: 12px; color: #374151;'>"
        "Loading booking widget... If this persists, verify widget JS/CSS URLs."
        "</div>"
        "</div>"
        f"<script id='monobook-widget-bootstrap' type='application/json'>{bootstrap}</script>"
        f"{script_tag}"
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
        "Use search_hotels for cross-property hotel discovery by location and filters. "
        "Use property-specific tools search_rooms, check_availability, and create_booking "
        "when you already have a valid UUID property_id. Always pass ISO dates."
    ),
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


@mcp_server.tool(
    name="search_hotels",
    description=(
        "Search hotels across properties by query, location, and room constraints. "
        "Supports city/country/property name/room name/coordinates, availability, guests, "
        "pet-friendly, and budget filters."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=HOTELS_WIDGET_URI,
        invoking="Searching hotels...",
        invoked="Hotel results ready.",
    ),
    structured_output=True,
)
async def mcp_search_hotels(
    query: str = "",
    property_name: str | None = None,
    city: str | None = None,
    country: str | None = None,
    room_name: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = 20.0,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int | None = None,
    pet_friendly: bool | None = None,
    budget_per_night_max: float | None = None,
    budget_total_max: float | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    client = get_supabase_client()
    session_id = _session_id(ctx)

    result = await search_hotels(
        client=client,
        query=query,
        property_name=property_name,
        city=city,
        country=country,
        room_name=room_name,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        pet_friendly=pet_friendly,
        budget_per_night_max=budget_per_night_max,
        budget_total_max=budget_total_max,
        session_id=session_id,
        source="chatgpt",
    )
    if "error" in result:
        return _tool_error(str(result["error"]), "search_hotels")

    count = result.get("count_hotels", 0)
    return _tool_result(
        text=f"Found {count} hotel(s).",
        structured_content=result,
        widget="search_hotels",
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
    HOTELS_WIDGET_URI,
    name="Monobook Hotel Discovery Widget",
    description="Interactive hotel discovery widget for cross-property search.",
    mime_type="text/html",
    meta=_resource_meta(
        "Browse matched hotels and rooms across locations with advanced filters."
    ),
)
def mcp_search_hotels_widget() -> str:
    return _render_widget_html("search_hotels")


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

    await _refresh_widget_asset_cache()
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
