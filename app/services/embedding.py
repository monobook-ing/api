from __future__ import annotations

import json
import logging
from typing import Any

from supabase import Client

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on environment package version
    OpenAI = None  # type: ignore[assignment]

from app.core.config import get_settings
from app.crud.currency import (
    get_currency_display_map,
    normalize_currency_code,
    resolve_currency_display,
)

logger = logging.getLogger(__name__)

settings = get_settings()


def _get_openai_client(api_key: str) -> Any:
    if OpenAI is None:
        raise RuntimeError("OpenAI client is unavailable. Install openai>=1.0.0")
    return OpenAI(api_key=api_key)


async def generate_embedding(text: str, api_key: str) -> list[float]:
    """Generate a 1536-dim embedding via OpenAI text-embedding-3-small."""
    client = _get_openai_client(api_key)
    response = client.embeddings.create(
        input=text,
        model=settings.embedding_model,
    )
    return response.data[0].embedding


async def _upsert_embedding(
    client: Client,
    property_id: str,
    source_type: str,
    source_id: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    metadata: dict | None = None,
) -> dict:
    """Insert or update an embedding row. Deletes old row for same source first."""
    # Remove existing embedding for this source+chunk
    client.table("embeddings").delete().eq(
        "source_type", source_type
    ).eq("source_id", source_id).eq("chunk_index", chunk_index).execute()

    row = {
        "property_id": property_id,
        "source_type": source_type,
        "source_id": source_id,
        "chunk_index": chunk_index,
        "content": content,
        "embedding": json.dumps(embedding),
        "metadata": metadata or {},
    }
    response = client.table("embeddings").insert(row).execute()
    return response.data[0] if response.data else {}


async def embed_property(client: Client, property_id: str, api_key: str) -> int:
    """Generate and store embeddings for a property. Returns count of embeddings created."""
    # Fetch property
    prop = (
        client.table("properties")
        .select("*, accounts(name)")
        .eq("id", property_id)
        .single()
        .execute()
    )
    if not prop.data:
        return 0

    p = prop.data
    account = p.pop("accounts", None)
    property_name = account["name"] if account else ""

    # Fetch rooms for amenities aggregation
    rooms = (
        client.table("rooms")
        .select("name, type, amenities, description")
        .eq("property_id", property_id)
        .eq("status", "active")
        .execute()
    )
    room_amenities = set()
    room_descriptions = []
    for r in rooms.data or []:
        for a in r.get("amenities") or []:
            room_amenities.add(a)
        if r.get("description"):
            room_descriptions.append(f"{r['name']} ({r['type']}): {r['description']}")

    # Build semantic text
    parts = [f"Property: {property_name}"]
    if p.get("description"):
        parts.append(p["description"])
    if p.get("city"):
        location_parts = [p.get("city"), p.get("state"), p.get("country")]
        parts.append("Location: " + ", ".join(x for x in location_parts if x))
    if room_amenities:
        parts.append("Amenities: " + ", ".join(sorted(room_amenities)))
    if room_descriptions:
        parts.append("Rooms: " + "; ".join(room_descriptions))

    text = "\n".join(parts)
    embedding = await generate_embedding(text, api_key)
    await _upsert_embedding(
        client,
        property_id,
        "property",
        property_id,
        0,
        text,
        embedding,
        {"name": property_name, "city": p.get("city")},
    )
    return 1


async def embed_room(
    client: Client, room_id: str, property_id: str, api_key: str
) -> int:
    """Generate and store embedding for a single room."""
    room = (
        client.table("rooms")
        .select("*")
        .eq("id", room_id)
        .single()
        .execute()
    )
    if not room.data:
        return 0

    r = room.data
    currency_code = normalize_currency_code(r.get("currency_code"))
    currency_display_map = await get_currency_display_map(client, [currency_code])
    currency_display = resolve_currency_display(currency_code, currency_display_map)
    parts = [f"Room: {r['name']} ({r['type']})"]
    if r.get("description"):
        parts.append(r["description"])
    if any(ch.isalpha() for ch in currency_display):
        price_text = f"{r['price_per_night']} {currency_display}/night"
    else:
        price_text = f"{currency_display}{r['price_per_night']}/night"
    parts.append(f"Price: {price_text}, Max guests: {r['max_guests']}")
    if r.get("bed_config"):
        parts.append(f"Bed: {r['bed_config']}")
    if r.get("amenities"):
        parts.append("Amenities: " + ", ".join(r["amenities"]))

    text = "\n".join(parts)
    embedding = await generate_embedding(text, api_key)
    await _upsert_embedding(
        client,
        property_id,
        "room",
        room_id,
        0,
        text,
        embedding,
        {"name": r["name"], "type": r["type"], "price": str(r["price_per_night"])},
    )
    return 1


async def embed_all_rooms(client: Client, property_id: str, api_key: str) -> int:
    """Embed all active rooms for a property. Returns count."""
    rooms = (
        client.table("rooms")
        .select("id")
        .eq("property_id", property_id)
        .eq("status", "active")
        .execute()
    )
    count = 0
    for r in rooms.data or []:
        count += await embed_room(client, r["id"], property_id, api_key)
    return count


async def embed_knowledge_chunks(
    client: Client,
    file_id: str,
    property_id: str,
    chunks: list[str],
    api_key: str,
    file_name: str = "",
) -> int:
    """Embed pre-chunked knowledge file text. Returns count."""
    # Remove old embeddings for this file
    client.table("embeddings").delete().eq(
        "source_type", "knowledge_chunk"
    ).eq("source_id", file_id).execute()

    count = 0
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        embedding = await generate_embedding(chunk, api_key)
        await _upsert_embedding(
            client,
            property_id,
            "knowledge_chunk",
            file_id,
            i,
            chunk,
            embedding,
            {"file_name": file_name, "chunk_index": i},
        )
        count += 1
    return count


async def search_similar(
    client: Client,
    property_id: str,
    query: str,
    api_key: str,
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict]:
    """Semantic search: generate query embedding and call match_embeddings RPC."""
    query_embedding = await generate_embedding(query, api_key)
    response = client.rpc(
        "match_embeddings",
        {
            "query_embedding": json.dumps(query_embedding),
            "match_property_id": property_id,
            "match_threshold": threshold,
            "match_count": limit,
        },
    ).execute()
    return response.data or []
