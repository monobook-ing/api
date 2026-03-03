from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
from supabase import Client

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_GOOGLE_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_GOOGLE_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

_PRICE_ENUM_BY_LEVEL = {
    0: "PRICE_LEVEL_FREE",
    1: "PRICE_LEVEL_INEXPENSIVE",
    2: "PRICE_LEVEL_MODERATE",
    3: "PRICE_LEVEL_EXPENSIVE",
    4: "PRICE_LEVEL_VERY_EXPENSIVE",
}

_PRICE_LEVEL_BY_ENUM = {v: k for k, v in _PRICE_ENUM_BY_LEVEL.items()}

_FIELD_MASK_SEARCH = ",".join(
    [
        "places.id",
        "places.name",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.types",
        "places.internationalPhoneNumber",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.photos",
        "places.regularOpeningHours",
        "places.currentOpeningHours",
        "places.googleMapsUri",
    ]
)

_FIELD_MASK_DETAILS = ",".join(
    [
        "id",
        "name",
        "displayName",
        "formattedAddress",
        "location",
        "rating",
        "userRatingCount",
        "priceLevel",
        "types",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "websiteUri",
        "photos",
        "regularOpeningHours",
        "currentOpeningHours",
        "googleMapsUri",
    ]
)

_IGNORED_TYPES = {
    "point_of_interest",
    "establishment",
    "food",
    "restaurant",
}


class PlacesService:
    """Google Places API wrapper with Supabase-backed cache."""

    @classmethod
    async def search_nearby(
        cls,
        client: Client,
        lat: float,
        lng: float,
        radius_m: int | None,
        query: str,
        cuisine: str,
        price_level: int,
        open_now: bool,
        limit: int,
        api_key: str,
    ) -> list[dict[str, Any]]:
        if not api_key:
            raise RuntimeError("Google Places API key is not configured.")

        safe_limit = max(1, min(limit, 20))
        radius = max(100, min(int(radius_m or settings.places_default_radius_m), 50000))

        cache_payload = {
            "kind": "search_nearby",
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "radius": radius,
            "query": query,
            "cuisine": cuisine,
            "price_level": price_level,
            "open_now": open_now,
            "limit": safe_limit,
        }
        cache_key = cls._build_cache_key(cache_payload)
        cached = await cls._check_cache(client, cache_key)

        if cached is not None:
            places = cached.get("places", [])
            return [
                cls._normalize_google_place(place, api_key=api_key)
                for place in places[:safe_limit]
            ]

        text_terms = [query.strip() or "restaurant"]
        if cuisine.strip():
            text_terms.append(cuisine.strip())
        payload: dict[str, Any] = {
            "textQuery": " ".join(text_terms),
            "includedType": "restaurant",
            "maxResultCount": safe_limit,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius),
                }
            },
            "rankPreference": "DISTANCE",
            "openNow": bool(open_now),
        }
        if price_level > 0 and price_level in _PRICE_ENUM_BY_LEVEL:
            payload["priceLevels"] = [_PRICE_ENUM_BY_LEVEL[price_level]]

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _FIELD_MASK_SEARCH,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as http_client:
                response = await http_client.post(
                    _GOOGLE_SEARCH_TEXT_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Google Places search_nearby failed: %s", exc)
            return []

        await cls._store_cache(
            client,
            cache_key,
            data,
            settings.places_cache_ttl_seconds,
        )

        places = data.get("places", [])
        return [
            cls._normalize_google_place(place, api_key=api_key)
            for place in places[:safe_limit]
        ]

    @classmethod
    async def get_place_details(
        cls,
        client: Client,
        place_id: str,
        api_key: str,
    ) -> dict[str, Any]:
        if not api_key:
            raise RuntimeError("Google Places API key is not configured.")

        normalized_place_id = (place_id or "").strip()
        if not normalized_place_id:
            return {}

        cache_key = cls._build_cache_key(
            {"kind": "get_place_details", "place_id": normalized_place_id}
        )
        cached = await cls._check_cache(client, cache_key)
        if cached is not None:
            return cls._normalize_google_place(cached, api_key=api_key)

        details_url = _GOOGLE_PLACE_DETAILS_URL.format(
            place_id=quote(normalized_place_id, safe="")
        )
        headers = {
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _FIELD_MASK_DETAILS,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as http_client:
                response = await http_client.get(details_url, headers=headers)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Google Places get_place_details failed: %s", exc)
            return {}

        await cls._store_cache(
            client,
            cache_key,
            data,
            settings.places_cache_ttl_seconds,
        )
        return cls._normalize_google_place(data, api_key=api_key)

    @staticmethod
    def _build_cache_key(params: dict[str, Any]) -> str:
        serialized = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    async def _check_cache(client: Client, cache_key: str) -> dict[str, Any] | None:
        now_iso = datetime.now(timezone.utc).isoformat()
        response = (
            client.table("places_cache")
            .select("response_data")
            .eq("cache_key", cache_key)
            .gt("expires_at", now_iso)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None

        payload = response.data[0].get("response_data")
        return payload if isinstance(payload, dict) else None

    @staticmethod
    async def _store_cache(
        client: Client,
        cache_key: str,
        data: dict[str, Any],
        ttl: int,
    ) -> None:
        if ttl <= 0:
            return

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        client.table("places_cache").upsert(
            {
                "cache_key": cache_key,
                "response_data": data,
                "expires_at": expires_at.isoformat(),
            },
            on_conflict="cache_key",
        ).execute()

    @classmethod
    def _normalize_google_place(
        cls,
        raw: dict[str, Any],
        *,
        api_key: str,
    ) -> dict[str, Any]:
        place_id = cls._extract_place_id(raw)
        location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
        lat = cls._to_float_or_none(location.get("latitude"))
        lng = cls._to_float_or_none(location.get("longitude"))
        price_level = cls._normalize_price_level(raw.get("priceLevel"))

        maps_url = raw.get("googleMapsUri")
        if not maps_url:
            if place_id:
                maps_url = (
                    "https://www.google.com/maps/search/?api=1"
                    f"&query_place_id={place_id}"
                )
            elif lat is not None and lng is not None:
                maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

        opening_hours = cls._normalize_opening_hours(raw)

        return {
            "place_id": place_id,
            "source": "google",
            "name": cls._display_name(raw),
            "address": raw.get("formattedAddress"),
            "lat": lat,
            "lng": lng,
            "rating": cls._to_float_or_none(raw.get("rating")),
            "review_count": cls._to_int_or_none(raw.get("userRatingCount")),
            "price_level": price_level,
            "cuisine": cls._extract_cuisine(raw.get("types")),
            "phone": raw.get("internationalPhoneNumber") or raw.get("nationalPhoneNumber"),
            "website": raw.get("websiteUri"),
            "photo_url": cls._photo_url(raw.get("photos"), api_key=api_key),
            "opening_hours": opening_hours,
            "is_open_now": cls._extract_open_now(raw),
            "walking_minutes": None,
            "distance_m": None,
            "best_for": [],
            "meal_types": [],
            "is_curated": False,
            "is_sponsored": False,
            "maps_url": maps_url,
        }

    @staticmethod
    def _extract_place_id(raw: dict[str, Any]) -> str:
        if isinstance(raw.get("id"), str):
            return raw["id"]
        name = raw.get("name")
        if isinstance(name, str) and "/" in name:
            return name.split("/")[-1]
        return ""

    @staticmethod
    def _display_name(raw: dict[str, Any]) -> str:
        display_name = raw.get("displayName")
        if isinstance(display_name, dict):
            text = display_name.get("text")
            if isinstance(text, str):
                return text
        if isinstance(display_name, str):
            return display_name
        return "Unknown place"

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_price_level(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value if 0 <= value <= 4 else None
        if isinstance(value, str):
            return _PRICE_LEVEL_BY_ENUM.get(value)
        return None

    @staticmethod
    def _extract_cuisine(types: Any) -> list[str]:
        if not isinstance(types, list):
            return []

        labels: list[str] = []
        for place_type in types:
            if not isinstance(place_type, str) or place_type in _IGNORED_TYPES:
                continue
            label = place_type.replace("_", " ").strip().title()
            if label and label not in labels:
                labels.append(label)
            if len(labels) >= 4:
                break
        return labels

    @classmethod
    def _normalize_opening_hours(cls, raw: dict[str, Any]) -> dict[str, Any] | None:
        source = raw.get("regularOpeningHours")
        if not isinstance(source, dict):
            source = raw.get("currentOpeningHours") if isinstance(raw.get("currentOpeningHours"), dict) else None
        if not isinstance(source, dict):
            return None

        weekday = source.get("weekdayDescriptions")
        if not isinstance(weekday, list):
            return None

        normalized: dict[str, Any] = {}
        for row in weekday:
            if not isinstance(row, str) or ":" not in row:
                continue
            day, value = row.split(":", 1)
            normalized[day.strip().lower()] = value.strip()

        return normalized or None

    @staticmethod
    def _extract_open_now(raw: dict[str, Any]) -> bool | None:
        current = raw.get("currentOpeningHours")
        if isinstance(current, dict) and isinstance(current.get("openNow"), bool):
            return current.get("openNow")
        regular = raw.get("regularOpeningHours")
        if isinstance(regular, dict) and isinstance(regular.get("openNow"), bool):
            return regular.get("openNow")
        return None

    @staticmethod
    def _photo_url(photos: Any, *, api_key: str) -> str | None:
        if not isinstance(photos, list) or not photos:
            return None
        first = photos[0] if isinstance(photos[0], dict) else None
        if not isinstance(first, dict):
            return None
        photo_name = first.get("name")
        if not isinstance(photo_name, str) or not photo_name:
            return None
        return (
            f"https://places.googleapis.com/v1/{photo_name}/media"
            f"?maxHeightPx=600&key={quote(api_key, safe='')}"
        )
