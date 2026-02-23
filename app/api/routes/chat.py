"""Chat API routes — guest-facing, no JWT auth required.

Endpoints:
  POST /v1.0/properties/{property_id}/chat/sessions — create session
  POST /v1.0/properties/{property_id}/chat/sessions/{session_id}/messages — send message (SSE stream)
  GET  /v1.0/properties/{property_id}/chat/sessions/{session_id}/messages — get history
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict

from agents import Runner
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from supabase import Client

from app.agents.definitions import build_agents
from app.agents.guardrails import sanitize_input
from app.api.deps import validate_property_id
from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.crud.chat import create_message, create_session, get_messages, get_session
from app.db.base import get_supabase
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(
    prefix="/v1.0/properties/{property_id}/chat", tags=["chat"]
)

# Simple in-memory rate limiter: IP -> list of timestamps
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 20  # max messages per window
RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(ip: str) -> bool:
    """Returns True if within rate limit, False if exceeded."""
    now = time.time()
    timestamps = _rate_limit_store[ip]
    # Clean old entries
    _rate_limit_store[ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limit_store[ip].append(now)
    return True


async def _get_api_key(client: Client, property_id: str) -> str:
    """Get OpenAI API key: property-level first, then platform fallback."""
    key = await get_decrypted_api_key(client, property_id, "openai")
    if key:
        return key
    if settings.openai_api_key:
        return settings.openai_api_key
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI chat is not configured for this property.",
    )


def _verify_property_exists(client: Client, property_id: str) -> None:
    """Verify that the property_id is a valid UUID and the property exists."""
    validate_property_id(property_id)
    result = client.table("properties").select("id").eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Property not found"
        )


@router.post("/sessions", response_model=ChatSessionResponse)
async def start_chat_session(
    property_id: str,
    payload: ChatSessionCreate,
    request: Request,
    client: Client = Depends(get_supabase),
):
    """Create a new chat session for a guest."""
    _verify_property_exists(client, property_id)

    session = await create_session(
        client,
        property_id,
        payload.source,
        payload.guest_name,
        payload.guest_email,
    )
    return session


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageListResponse,
)
async def list_chat_messages(
    property_id: str,
    session_id: str,
    client: Client = Depends(get_supabase),
):
    """Get message history for a chat session."""
    validate_property_id(property_id)
    session = await get_session(client, session_id)
    if not session or session["property_id"] != property_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    messages = await get_messages(client, session_id)
    return ChatMessageListResponse(
        items=[ChatMessageResponse(**m) for m in messages]
    )


@router.post("/sessions/{session_id}/messages")
async def send_chat_message(
    property_id: str,
    session_id: str,
    payload: ChatMessageCreate,
    request: Request,
    client: Client = Depends(get_supabase),
):
    """Send a message and get AI response via SSE stream."""
    # Validate property_id format
    validate_property_id(property_id)

    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before sending more messages.",
        )

    # Verify session
    session = await get_session(client, session_id)
    if not session or session["property_id"] != property_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Get API key
    api_key = await _get_api_key(client, property_id)

    # Sanitize input
    content = sanitize_input(payload.content)

    # Save user message
    await create_message(client, session_id, "user", content)

    # Build agent system
    agent, context, run_config = build_agents(
        client, property_id, api_key, session_id, settings.agent_model
    )

    # Load conversation history
    history = await get_messages(client, session_id, limit=30)
    input_messages = []
    for msg in history:
        if msg["role"] in ("user", "assistant"):
            input_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    async def event_stream():
        """SSE event generator."""
        full_response = ""
        try:
            # Send start event
            yield f"data: {json.dumps({'type': 'message_start'})}\n\n"

            # Run agent with streaming
            result = Runner.run_streamed(
                agent,
                input=input_messages,
                context=context,
                run_config=run_config,
            )

            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    # Extract text deltas from raw OpenAI response
                    raw = event.data
                    if hasattr(raw, "type"):
                        if raw.type == "response.output_text.delta":
                            delta = raw.delta if hasattr(raw, "delta") else ""
                            if delta:
                                full_response += delta
                                yield f"data: {json.dumps({'type': 'text_delta', 'delta': delta})}\n\n"
                        elif raw.type == "response.function_call_arguments.done":
                            tool_name = getattr(raw, "name", "unknown")
                            yield f"data: {json.dumps({'type': 'tool_use', 'tool': tool_name})}\n\n"
                elif event.type == "agent_updated_stream_event":
                    agent_name = event.new_agent.name if event.new_agent else "unknown"
                    yield f"data: {json.dumps({'type': 'agent_handoff', 'agent': agent_name})}\n\n"

            # Get final output
            final_result = result.final_output
            if final_result and not full_response:
                full_response = str(final_result)
                yield f"data: {json.dumps({'type': 'text_delta', 'delta': full_response})}\n\n"

            # Save assistant message
            if full_response:
                await create_message(client, session_id, "assistant", full_response)

            # Send end event
            yield f"data: {json.dumps({'type': 'message_end', 'content': full_response})}\n\n"

        except Exception as e:
            logger.error(f"Agent error: {e}")
            error_msg = "I'm sorry, I encountered an issue. Please try again."
            await create_message(client, session_id, "assistant", error_msg)
            yield f"data: {json.dumps({'type': 'text_delta', 'delta': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'message_end', 'content': error_msg})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
