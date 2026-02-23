"""Multi-agent system using OpenAI Agents SDK.

Three agents with handoff pattern:
  Triage Agent → Hotel Search Agent (find rooms, property info, knowledge base)
  Triage Agent → Booking Agent (availability, pricing, create booking)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents import Agent, Runner, function_tool, handoff, RunContextWrapper, RunConfig
from supabase import Client

from app.agents.guardrails import sanitize_input
from app.agents.tools import (
    calculate_price,
    check_availability,
    get_property_info,
    get_room_details,
    search_knowledge_base,
    search_rooms,
    tool_create_booking,
    tool_get_booking_status,
)

logger = logging.getLogger(__name__)


class AgentContext:
    """Shared context passed to all agent tool calls."""

    def __init__(
        self,
        client: Client,
        property_id: str,
        api_key: str,
        session_id: str | None = None,
    ):
        self.client = client
        self.property_id = property_id
        self.api_key = api_key
        self.session_id = session_id


# -- Hotel Search Agent Tools (wrapped for agents SDK) --


@function_tool
async def tool_search_rooms(
    ctx: RunContextWrapper[AgentContext],
    query: str,
    check_in: str = "",
    check_out: str = "",
    guests: int = 2,
) -> str:
    """Search for available rooms matching a query. Use natural language to describe what the guest wants."""
    c = ctx.context
    result = await search_rooms(
        c.client, c.property_id, c.api_key,
        query,
        check_in or None, check_out or None,
        guests if guests > 0 else None,
        c.session_id,
    )
    return json.dumps(result)


@function_tool
async def tool_get_property_info(ctx: RunContextWrapper[AgentContext]) -> str:
    """Get information about the property (name, description, location, host details)."""
    c = ctx.context
    result = await get_property_info(c.client, c.property_id, c.session_id)
    return json.dumps(result)


@function_tool
async def tool_get_room_details(
    ctx: RunContextWrapper[AgentContext], room_id: str
) -> str:
    """Get detailed information about a specific room including pricing tiers."""
    c = ctx.context
    result = await get_room_details(c.client, c.property_id, room_id, c.session_id)
    return json.dumps(result)


@function_tool
async def tool_search_knowledge(
    ctx: RunContextWrapper[AgentContext], query: str
) -> str:
    """Search the hotel's knowledge base (policies, FAQ, amenities, rules)."""
    c = ctx.context
    result = await search_knowledge_base(
        c.client, c.property_id, c.api_key, query, c.session_id
    )
    return json.dumps(result)


# -- Booking Agent Tools (wrapped for agents SDK) --


@function_tool
async def tool_check_availability(
    ctx: RunContextWrapper[AgentContext],
    room_id: str,
    check_in: str,
    check_out: str,
) -> str:
    """Check if a specific room is available for the given dates (YYYY-MM-DD format)."""
    c = ctx.context
    result = await check_availability(
        c.client, c.property_id, room_id, check_in, check_out, c.session_id
    )
    return json.dumps(result)


@function_tool
async def tool_calculate_price(
    ctx: RunContextWrapper[AgentContext],
    room_id: str,
    check_in: str,
    check_out: str,
    guests: int = 2,
) -> str:
    """Calculate the total price for a room booking including taxes and fees."""
    c = ctx.context
    result = await calculate_price(
        c.client, c.property_id, room_id, check_in, check_out, guests, c.session_id
    )
    return json.dumps(result)


@function_tool
async def tool_book_room(
    ctx: RunContextWrapper[AgentContext],
    room_id: str,
    guest_name: str,
    check_in: str,
    check_out: str,
    guest_email: str = "",
    guests: int = 2,
) -> str:
    """Create a booking for a guest. Requires room_id, guest name, and dates."""
    c = ctx.context
    result = await tool_create_booking(
        c.client, c.property_id, room_id, guest_name,
        guest_email or None, check_in, check_out, guests, c.session_id
    )
    return json.dumps(result)


@function_tool
async def tool_booking_status(
    ctx: RunContextWrapper[AgentContext], booking_id: str
) -> str:
    """Get the status of an existing booking by its ID."""
    c = ctx.context
    result = await tool_get_booking_status(
        c.client, c.property_id, booking_id, c.session_id
    )
    return json.dumps(result)


# -- Agent Definitions --

hotel_search_agent = Agent[AgentContext](
    name="Hotel Search Agent",
    instructions="""You are a hotel search specialist. Help guests find the perfect room.

Your capabilities:
- Search for rooms by description, amenities, dates, and guest count
- Get detailed property information (location, description, host)
- Get detailed room information (pricing tiers, amenities, bed config)
- Search the hotel knowledge base for policies, rules, and FAQ

When presenting rooms, be descriptive and highlight key features.
Always include the price per night and amenities.
Use the runtime server datetime provided in the system message for all date reasoning.
If a guest provides dates without a year, interpret them as the next valid occurrence not in the past, then confirm.
If the guest wants to book, hand off to the Booking Agent.

Respond in the same language the guest uses.""",
    tools=[
        tool_search_rooms,
        tool_get_property_info,
        tool_get_room_details,
        tool_search_knowledge,
    ],
)

booking_agent = Agent[AgentContext](
    name="Booking Agent",
    instructions="""You are a booking specialist. Help guests complete their reservations.

Your capabilities:
- Check room availability for specific dates
- Calculate total price (including taxes 12% and service fee 4%)
- Create bookings with guest details
- Check existing booking status

Booking flow:
1. Verify room availability
2. Calculate and present the price breakdown
3. Ask for guest name and email
4. Create the booking

Always confirm the total price before creating a booking.
Use the runtime server datetime provided in the system message as the only source of truth for "today".
For date inputs without a year, interpret as the next valid occurrence not in the past, then confirm exact YYYY-MM-DD dates.
Do not claim a date is in the past or a room is unavailable without checking via booking tools first.
If the guest wants to search for different rooms, hand off to the Hotel Search Agent.

Respond in the same language the guest uses.""",
    tools=[
        tool_check_availability,
        tool_calculate_price,
        tool_book_room,
        tool_booking_status,
    ],
)

# Add handoffs
hotel_search_agent.handoffs = [handoff(booking_agent)]
booking_agent.handoffs = [handoff(hotel_search_agent)]

triage_agent = Agent[AgentContext](
    name="Concierge",
    instructions="""You are a friendly hotel concierge AI assistant for this property.

Your role:
- Greet guests warmly and understand what they need
- For room searches, availability questions, or property information → hand off to Hotel Search Agent
- For bookings, pricing, or reservation management → hand off to Booking Agent
- For general questions about the hotel, answer directly using your knowledge

Be concise, helpful, and professional. Use emojis sparingly.
Respond in the same language the guest uses.
Use the runtime server datetime provided in the system message for all date interpretations.
If the guest starts by describing what they want (dates, room type, budget), immediately hand off to the appropriate agent.""",
    handoffs=[
        handoff(hotel_search_agent),
        handoff(booking_agent),
    ],
)


def build_agents(
    client: Client,
    property_id: str,
    api_key: str,
    session_id: str | None = None,
    model: str = "gpt-4o-mini",
) -> tuple[Agent[AgentContext], AgentContext, RunConfig]:
    """Build the agent system with shared context.

    Returns (triage_agent, context, run_config).
    """
    context = AgentContext(
        client=client,
        property_id=property_id,
        api_key=api_key,
        session_id=session_id,
    )

    run_config = RunConfig(model=model)

    return triage_agent, context, run_config
