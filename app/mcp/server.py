from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from html import escape
from typing import Any
from urllib.parse import urlparse

from starlette.types import ASGIApp
from supabase import Client

try:
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.types import ToolAnnotations
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    class Context:  # type: ignore[no-redef]
        request_id: Any | None = None

    class TransportSecuritySettings:  # type: ignore[no-redef]
        def __init__(self, **_kwargs: Any) -> None:
            pass

    class ToolAnnotations:  # type: ignore[no-redef]
        def __init__(self, **_kwargs: Any) -> None:
            pass

    class _FallbackSessionManager:
        @asynccontextmanager
        async def run(self):
            yield

    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._session_manager = _FallbackSessionManager()

        @property
        def session_manager(self) -> _FallbackSessionManager:
            return self._session_manager

        def tool(self, *_args: Any, **_kwargs: Any):
            def decorator(func):
                return func

            return decorator

        def resource(self, *_args: Any, **_kwargs: Any):
            def decorator(func):
                return func

            return decorator

        def streamable_http_app(self):
            async def app(scope, receive, send):  # type: ignore[no-untyped-def]
                raise RuntimeError("MCP runtime dependency is missing.")

            return app

from app.agents.tools import (
    _haversine_distance_km,
    check_availability,
    get_curated_places as get_curated_places_tool,
    search_places_nearby as search_places_nearby_tool,
    search_hotels,
    search_rooms,
    tool_create_booking,
)
from app.api.deps import validate_property_id
from app.core.config import get_settings
from app.crud.currency import (
    get_currency_display_map,
    normalize_currency_code,
    resolve_currency_display,
)
from app.crud.ai_connection import get_decrypted_api_key
from app.db.base import get_supabase_client
from app.mcp.auth import MCPHeaderAuthApp
from app.services.places import PlacesService

settings = get_settings()

SEARCH_WIDGET_URI = "ui://widget/search-rooms.html"
HOTELS_WIDGET_URI = "ui://widget/search-hotels.html"
AVAILABILITY_WIDGET_URI = "ui://widget/check-availability.html"
BOOKING_WIDGET_URI = "ui://widget/booking-confirmation.html"
RESTAURANT_WIDGET_URI = "ui://widget/restaurant-results.html"


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
        "<script>window.process=window.process||{env:{NODE_ENV:'production'}}</script>"
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


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _normalize_curated_place(row: dict[str, Any]) -> dict[str, Any]:
    lat = _to_float(row.get("lat"))
    lng = _to_float(row.get("lng"))
    photo_urls = _to_text_list(row.get("photo_urls"))
    maps_url = None
    google_place_id = row.get("google_place_id")
    if google_place_id:
        maps_url = (
            "https://www.google.com/maps/search/?api=1"
            f"&query_place_id={google_place_id}"
        )
    elif lat is not None and lng is not None:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

    return {
        "place_id": str(row.get("id", "")),
        "source": "curated",
        "name": row.get("name", ""),
        "address": row.get("address"),
        "lat": lat,
        "lng": lng,
        "rating": _to_float(row.get("rating")),
        "review_count": _to_int(row.get("review_count")),
        "price_level": _to_int(row.get("price_level")),
        "cuisine": _to_text_list(row.get("cuisine")),
        "phone": row.get("phone"),
        "website": row.get("website"),
        "photo_url": photo_urls[0] if photo_urls else None,
        "opening_hours": row.get("opening_hours"),
        "is_open_now": None,
        "walking_minutes": _to_int(row.get("walking_minutes")),
        "distance_m": None,
        "best_for": _to_text_list(row.get("best_for")),
        "meal_types": _to_text_list(row.get("meal_types")),
        "is_curated": True,
        "is_sponsored": bool(row.get("sponsored", False)),
        "maps_url": maps_url,
    }


def _attach_distance(
    place: dict[str, Any],
    property_lat: float | None,
    property_lng: float | None,
) -> dict[str, Any]:
    if property_lat is None or property_lng is None:
        return place
    place_lat = _to_float(place.get("lat"))
    place_lng = _to_float(place.get("lng"))
    if place_lat is None or place_lng is None:
        return place

    distance_km = _haversine_distance_km(property_lat, property_lng, place_lat, place_lng)
    distance_m = int(round(distance_km * 1000))
    updated = dict(place)
    updated["distance_m"] = distance_m
    if not updated.get("walking_minutes"):
        updated["walking_minutes"] = max(1, int(round(distance_m / 80)))
    return updated


async def _get_openai_api_key(client: Client, property_id: str) -> str:
    key = await get_decrypted_api_key(client, property_id, "openai")
    if key:
        return key
    if settings.openai_api_key:
        return settings.openai_api_key
    raise ValueError("OpenAI API key is not configured for this property.")


def _get_google_places_api_key() -> str:
    if settings.google_places_api_key:
        return settings.google_places_api_key
    raise ValueError("Google Places API key is not configured.")


mcp_server = FastMCP(
    name="Monobooking MCP Server",
    instructions=(
        "Use search_hotels for cross-property hotel discovery by location and filters. "
        "Use property-specific tools search_rooms, check_availability, and create_booking "
        "when you already have a valid UUID property_id. "
        "For dining recommendations, use search_places_nearby, get_curated_places, "
        "and get_place_details. Always pass ISO dates."
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
    name="search_places_nearby",
    description=(
        "Search restaurants near a property. Returns curated recommendations first, "
        "plus additional nearby options from Google Places."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=True,
    ),
    meta=_tool_meta(
        output_template=RESTAURANT_WIDGET_URI,
        invoking="Searching restaurants...",
        invoked="Restaurant results ready.",
    ),
    structured_output=True,
)
async def mcp_search_places_nearby(
    property_id: str,
    query: str = "restaurant",
    cuisine: str = "",
    price_level: int = 0,
    open_now: bool = False,
    limit: int = 8,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    result = await search_places_nearby_tool(
        client=client,
        property_id=property_id,
        query=query,
        cuisine=cuisine,
        price_level=price_level,
        open_now=open_now,
        limit=limit,
        session_id=session_id,
        source="chatgpt",
    )
    if "error" in result:
        return _tool_error(str(result["error"]), "restaurant_results")

    return _tool_result(
        text=(
            f"Found {result.get('count_curated', 0)} curated and "
            f"{result.get('count_nearby', 0)} nearby restaurant(s)."
        ),
        structured_content=result,
        widget="restaurant_results",
    )


@mcp_server.tool(
    name="get_curated_places",
    description="Get the property's curated restaurant recommendations.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=RESTAURANT_WIDGET_URI,
        invoking="Loading curated recommendations...",
        invoked="Curated recommendations ready.",
    ),
    structured_output=True,
)
async def mcp_get_curated_places(
    property_id: str,
    meal_type: str = "",
    tags: str = "",
    limit: int = 5,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    result = await get_curated_places_tool(
        client=client,
        property_id=property_id,
        meal_type=meal_type,
        tags=tags,
        limit=limit,
        session_id=session_id,
        source="chatgpt",
    )
    if "error" in result:
        return _tool_error(str(result["error"]), "restaurant_results")

    return _tool_result(
        text=f"Loaded {result.get('count_curated', 0)} curated recommendation(s).",
        structured_content=result,
        widget="restaurant_results",
    )


@mcp_server.tool(
    name="get_place_details",
    description="Get details for a curated place or a Google place ID.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=RESTAURANT_WIDGET_URI,
        invoking="Loading place details...",
        invoked="Place details ready.",
    ),
    structured_output=True,
)
async def mcp_get_place_details(
    property_id: str,
    place_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()

    property_row = (
        client.table("properties")
        .select("lat, lng")
        .eq("id", property_id)
        .limit(1)
        .execute()
    )
    prop = property_row.data[0] if property_row.data else {}
    prop_lat = _to_float(prop.get("lat"))
    prop_lng = _to_float(prop.get("lng"))

    curated = (
        client.table("curated_places")
        .select("*")
        .eq("property_id", property_id)
        .eq("id", place_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    curated_row = curated.data[0] if curated.data else None
    if curated_row is None:
        fallback = (
            client.table("curated_places")
            .select("*")
            .eq("property_id", property_id)
            .eq("google_place_id", place_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        curated_row = fallback.data[0] if fallback.data else None

    if curated_row:
        place = _attach_distance(_normalize_curated_place(curated_row), prop_lat, prop_lng)
        return _tool_result(
            text=f"Loaded details for {place.get('name', 'the place')}.",
            structured_content={"property_id": property_id, "place": place},
            widget="restaurant_results",
        )

    try:
        api_key = _get_google_places_api_key()
    except ValueError as exc:
        return _tool_error(str(exc), "restaurant_results")

    details = await PlacesService.get_place_details(client, place_id, api_key)
    if not details or not details.get("place_id"):
        return _tool_error("Place details not found.", "restaurant_results")

    details = _attach_distance(details, prop_lat, prop_lng)
    return _tool_result(
        text=f"Loaded details for {details.get('name', 'the place')}.",
        structured_content={"property_id": property_id, "place": details},
        widget="restaurant_results",
    )


@mcp_server.tool(
    name="report_place_issue",
    description="Report an issue with a place recommendation.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=RESTAURANT_WIDGET_URI,
        invoking="Reporting issue...",
        invoked="Issue reported.",
    ),
    structured_output=True,
)
async def mcp_report_place_issue(
    property_id: str,
    place_id: str,
    place_source: str,
    issue_type: str,
    comment: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    inserted = (
        client.table("place_issues")
        .insert(
            {
                "property_id": property_id,
                "place_id": place_id,
                "place_source": place_source,
                "issue_type": issue_type,
                "comment": comment,
                "session_id": session_id,
                "resolved": False,
            }
        )
        .execute()
    )
    item = inserted.data[0] if inserted.data else {}
    return _tool_result(
        text="Issue reported.",
        structured_content={"ok": True, "issue": item},
        widget="restaurant_results",
    )


@mcp_server.tool(
    name="track_place_click",
    description="Track a CTA click (Directions, Reserve, Call) for restaurant cards.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta=_tool_meta(
        output_template=RESTAURANT_WIDGET_URI,
        invoking="Tracking interaction...",
        invoked="Interaction tracked.",
    ),
    structured_output=True,
)
async def mcp_track_place_click(
    property_id: str,
    place_id: str,
    place_source: str,
    context: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    validate_property_id(property_id)
    client = get_supabase_client()
    session_id = _session_id(ctx)

    inserted = (
        client.table("place_clicks")
        .insert(
            {
                "property_id": property_id,
                "place_id": place_id,
                "place_source": place_source,
                "context": context,
                "session_id": session_id,
            }
        )
        .execute()
    )
    item = inserted.data[0] if inserted.data else {}
    return _tool_result(
        text="Interaction tracked.",
        structured_content={"ok": True, "click": item},
        widget="restaurant_results",
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
        .select(
            "id, property_id, name, type, description, price_per_night, "
            "currency_code, max_guests, amenities, images"
        )
        .eq("id", room_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    if room_response.data:
        room = room_response.data
        currency_code = normalize_currency_code(room.get("currency_code"))
        currency_display_map = await get_currency_display_map(client, [currency_code])
        result["room"] = {
            "id": room["id"],
            "property_id": room["property_id"],
            "name": room["name"],
            "type": room["type"],
            "description": room.get("description", ""),
            "price_per_night": str(room["price_per_night"]),
            "currency_code": currency_code,
            "currency_display": resolve_currency_display(
                currency_code, currency_display_map
            ),
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


@mcp_server.resource(
    RESTAURANT_WIDGET_URI,
    name="Monobook Restaurant Results Widget",
    description="Interactive restaurant recommendation cards (curated + nearby).",
    mime_type="text/html",
    meta=_resource_meta(
        "Browse curated and nearby restaurant recommendations with quick actions."
    ),
)
def mcp_restaurant_widget() -> str:
    return _render_widget_html("restaurant_results")


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
