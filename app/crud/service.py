from __future__ import annotations

from datetime import datetime
from typing import Any

from supabase import Client


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = []
    previous_dash = False
    for char in lowered:
        if char.isalnum():
            cleaned.append(char)
            previous_dash = False
            continue
        if previous_dash:
            continue
        cleaned.append("-")
        previous_dash = True

    slug = "".join(cleaned).strip("-")
    return slug or f"item-{int(datetime.now().timestamp())}"


def _as_float(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return fallback


def _as_int(value: Any, fallback: int = 0) -> int:
    if value is None:
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _format_slot_time(raw: str | None) -> str:
    if not raw:
        return ""
    return raw[:5]


async def get_account_id_for_property(client: Client, property_id: str) -> str | None:
    response = (
        client.table("properties")
        .select("account_id")
        .eq("id", property_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0].get("account_id")


async def _load_categories_map(client: Client, account_id: str | None) -> dict[str, dict]:
    if not account_id:
        return {}
    response = (
        client.table("service_categories")
        .select("*")
        .eq("account_id", account_id)
        .execute()
    )
    return {row["id"]: row for row in (response.data or [])}


async def _load_partners_map(client: Client, account_id: str | None) -> dict[str, dict]:
    if not account_id:
        return {}
    response = (
        client.table("service_partners")
        .select("*")
        .eq("account_id", account_id)
        .execute()
    )
    return {row["id"]: row for row in (response.data or [])}


async def _load_slots_map(client: Client, service_ids: list[str]) -> dict[str, list[dict]]:
    if not service_ids:
        return {}
    response = (
        client.table("service_time_slots")
        .select("*")
        .in_("service_id", service_ids)
        .order("sort_order")
        .order("slot_time")
        .execute()
    )
    slots_by_service: dict[str, list[dict]] = {}
    for slot in response.data or []:
        normalized = {
            **slot,
            "time": _format_slot_time(slot.get("slot_time")),
            "capacity": _as_int(slot.get("capacity")),
            "booked": _as_int(slot.get("booked")),
            "sort_order": _as_int(slot.get("sort_order")),
        }
        slots_by_service.setdefault(slot["service_id"], []).append(normalized)
    return slots_by_service


def _normalize_service_row(
    row: dict,
    categories_by_id: dict[str, dict],
    partners_by_id: dict[str, dict],
    slots_by_service: dict[str, list[dict]],
) -> dict:
    category = categories_by_id.get(row.get("category_id"))
    partner = partners_by_id.get(row.get("partner_id"))
    image_urls = row.get("image_urls") or []
    if isinstance(image_urls, tuple):
        image_urls = list(image_urls)

    return {
        **row,
        "price": _as_float(row.get("price")),
        "vat_percent": _as_float(row.get("vat_percent")),
        "attach_rate": _as_float(row.get("attach_rate")),
        "conversion_rate": _as_float(row.get("conversion_rate")),
        "revenue_30d": _as_float(row.get("revenue_30d")),
        "total_bookings": _as_int(row.get("total_bookings")),
        "image_urls": image_urls if isinstance(image_urls, list) else [],
        "category_name": category.get("name") if category else None,
        "partner_name": partner.get("name") if partner else None,
        "slots": slots_by_service.get(row["id"], []),
    }


async def _ensure_unique_service_slug(
    client: Client,
    property_id: str,
    name: str,
    exclude_service_id: str | None = None,
) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 1
    while True:
        query = (
            client.table("services")
            .select("id")
            .eq("property_id", property_id)
            .eq("slug", candidate)
            .limit(1)
        )
        response = query.execute()
        found = response.data[0] if response.data else None
        if not found or found.get("id") == exclude_service_id:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


async def _ensure_unique_category_slug(
    client: Client,
    account_id: str,
    name: str,
    exclude_category_id: str | None = None,
) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 1
    while True:
        response = (
            client.table("service_categories")
            .select("id")
            .eq("account_id", account_id)
            .eq("slug", candidate)
            .limit(1)
            .execute()
        )
        found = response.data[0] if response.data else None
        if not found or found.get("id") == exclude_category_id:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


async def _ensure_unique_partner_slug(
    client: Client,
    account_id: str,
    name: str,
    exclude_partner_id: str | None = None,
) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 1
    while True:
        response = (
            client.table("service_partners")
            .select("id")
            .eq("account_id", account_id)
            .eq("slug", candidate)
            .limit(1)
            .execute()
        )
        found = response.data[0] if response.data else None
        if not found or found.get("id") == exclude_partner_id:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


async def _replace_service_slots(
    client: Client,
    service_id: str,
    slots: list[dict],
) -> None:
    client.table("service_time_slots").delete().eq("service_id", service_id).execute()
    if not slots:
        return
    rows = []
    for index, slot in enumerate(slots):
        rows.append(
            {
                "service_id": service_id,
                "slot_time": slot.get("time"),
                "capacity": _as_int(slot.get("capacity")),
                "booked": _as_int(slot.get("booked")),
                "sort_order": _as_int(slot.get("sort_order"), index),
            }
        )
    client.table("service_time_slots").insert(rows).execute()


async def list_service_categories(client: Client, property_id: str) -> list[dict]:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return []
    response = (
        client.table("service_categories")
        .select("*")
        .eq("account_id", account_id)
        .order("sort_order")
        .order("created_at")
        .execute()
    )
    return response.data or []


async def create_service_category(client: Client, property_id: str, data: dict) -> dict:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return {}
    slug = await _ensure_unique_category_slug(client, account_id, data.get("name", "category"))
    row = {
        "account_id": account_id,
        "slug": slug,
        "name": data.get("name", "Category"),
        "description": data.get("description") or "",
        "icon": data.get("icon") or "📦",
        "sort_order": _as_int(data.get("sort_order")),
    }
    response = client.table("service_categories").insert(row).execute()
    return response.data[0] if response.data else {}


async def update_service_category(
    client: Client,
    property_id: str,
    category_id: str,
    data: dict,
) -> dict | None:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return None
    existing = (
        client.table("service_categories")
        .select("*")
        .eq("id", category_id)
        .eq("account_id", account_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        return None

    filtered = {k: v for k, v in data.items() if v is not None}
    if "name" in filtered:
        filtered["slug"] = await _ensure_unique_category_slug(
            client, account_id, filtered["name"], exclude_category_id=category_id
        )
    if filtered:
        filtered["updated_at"] = datetime.utcnow().isoformat()
        (
            client.table("service_categories")
            .update(filtered)
            .eq("id", category_id)
            .eq("account_id", account_id)
            .execute()
        )

    result = (
        client.table("service_categories")
        .select("*")
        .eq("id", category_id)
        .eq("account_id", account_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


async def delete_service_category(client: Client, property_id: str, category_id: str) -> bool:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return False
    response = (
        client.table("service_categories")
        .delete()
        .eq("id", category_id)
        .eq("account_id", account_id)
        .execute()
    )
    return bool(response.data)


async def reorder_service_categories(
    client: Client,
    property_id: str,
    items: list[dict],
) -> list[dict]:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return []
    for item in items:
        (
            client.table("service_categories")
            .update(
                {
                    "sort_order": _as_int(item.get("sort_order")),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", item.get("id"))
            .eq("account_id", account_id)
            .execute()
        )
    return await list_service_categories(client, property_id)


async def list_service_partners(client: Client, property_id: str) -> list[dict]:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return []

    partners_response = (
        client.table("service_partners")
        .select("*")
        .eq("account_id", account_id)
        .order("created_at")
        .execute()
    )
    partners = partners_response.data or []
    if not partners:
        return []

    services_response = (
        client.table("services")
        .select("id, partner_id, status, revenue_30d")
        .eq("property_id", property_id)
        .not_.is_("partner_id", "null")
        .execute()
    )
    services = services_response.data or []
    service_ids = [row["id"] for row in services]

    active_services_by_partner: dict[str, int] = {}
    fallback_revenue_by_partner: dict[str, float] = {}
    service_partner_map: dict[str, str] = {}
    for service in services:
        partner_id = service.get("partner_id")
        if not partner_id:
            continue
        service_partner_map[service["id"]] = partner_id
        if service.get("status") == "active":
            active_services_by_partner[partner_id] = (
                active_services_by_partner.get(partner_id, 0) + 1
            )
        fallback_revenue_by_partner[partner_id] = (
            fallback_revenue_by_partner.get(partner_id, 0.0)
            + _as_float(service.get("revenue_30d"))
        )

    revenue_by_partner: dict[str, float] = {}
    if service_ids:
        bookings_response = (
            client.table("service_bookings")
            .select("service_id, total, status")
            .eq("property_id", property_id)
            .in_("service_id", service_ids)
            .execute()
        )
        for booking in bookings_response.data or []:
            if booking.get("status") == "cancelled":
                continue
            service_id = booking.get("service_id")
            partner_id = service_partner_map.get(service_id)
            if not partner_id:
                continue
            revenue_by_partner[partner_id] = (
                revenue_by_partner.get(partner_id, 0.0) + _as_float(booking.get("total"))
            )

    results = []
    for partner in partners:
        partner_id = partner["id"]
        revenue_generated = revenue_by_partner.get(
            partner_id, fallback_revenue_by_partner.get(partner_id, 0.0)
        )
        results.append(
            {
                **partner,
                "revenue_share_percent": _as_float(partner.get("revenue_share_percent")),
                "active_services": active_services_by_partner.get(partner_id, 0),
                "revenue_generated": revenue_generated,
            }
        )
    return results


async def create_service_partner(client: Client, property_id: str, data: dict) -> dict:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return {}
    slug = await _ensure_unique_partner_slug(client, account_id, data.get("name", "partner"))
    row = {
        "account_id": account_id,
        "slug": slug,
        "name": data.get("name", "Partner"),
        "revenue_share_percent": _as_float(data.get("revenue_share_percent")),
        "payout_type": data.get("payout_type") or "manual",
        "external_url": data.get("external_url"),
        "attribution_tracking": bool(data.get("attribution_tracking", False)),
        "status": data.get("status") or "active",
    }
    response = client.table("service_partners").insert(row).execute()
    return response.data[0] if response.data else {}


async def update_service_partner(
    client: Client,
    property_id: str,
    partner_id: str,
    data: dict,
) -> dict | None:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return None
    existing = (
        client.table("service_partners")
        .select("*")
        .eq("id", partner_id)
        .eq("account_id", account_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        return None

    nullable_fields = {"external_url"}
    filtered = {
        k: v
        for k, v in data.items()
        if v is not None or k in nullable_fields
    }
    if "name" in filtered:
        filtered["slug"] = await _ensure_unique_partner_slug(
            client, account_id, filtered["name"], exclude_partner_id=partner_id
        )
    if "revenue_share_percent" in filtered:
        filtered["revenue_share_percent"] = _as_float(filtered["revenue_share_percent"])
    if filtered:
        filtered["updated_at"] = datetime.utcnow().isoformat()
        (
            client.table("service_partners")
            .update(filtered)
            .eq("id", partner_id)
            .eq("account_id", account_id)
            .execute()
        )

    result = (
        client.table("service_partners")
        .select("*")
        .eq("id", partner_id)
        .eq("account_id", account_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


async def list_services(
    client: Client,
    property_id: str,
    *,
    search: str | None = None,
    type_filter: str | None = None,
    category_id: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    query = (
        client.table("services")
        .select("*")
        .eq("property_id", property_id)
        .order("created_at")
    )
    if type_filter:
        query = query.eq("type", type_filter)
    if category_id:
        query = query.eq("category_id", category_id)
    if status_filter:
        query = query.eq("status", status_filter)
    if search and search.strip():
        query = query.ilike("name", f"%{search.strip()}%")

    response = query.execute()
    rows = response.data or []
    if search and search.strip():
        lowered = search.strip().lower()
        rows = [
            row
            for row in rows
            if lowered in (row.get("name") or "").lower()
            or lowered in (row.get("short_description") or "").lower()
        ]

    account_id = rows[0].get("account_id") if rows else await get_account_id_for_property(
        client, property_id
    )
    categories_by_id = await _load_categories_map(client, account_id)
    partners_by_id = await _load_partners_map(client, account_id)
    slots_by_service = await _load_slots_map(client, [row["id"] for row in rows])
    return [
        _normalize_service_row(row, categories_by_id, partners_by_id, slots_by_service)
        for row in rows
    ]


async def get_service_by_id(client: Client, property_id: str, service_id: str) -> dict | None:
    response = (
        client.table("services")
        .select("*")
        .eq("id", service_id)
        .eq("property_id", property_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    row = response.data[0]
    categories_by_id = await _load_categories_map(client, row.get("account_id"))
    partners_by_id = await _load_partners_map(client, row.get("account_id"))
    slots_by_service = await _load_slots_map(client, [row["id"]])
    return _normalize_service_row(row, categories_by_id, partners_by_id, slots_by_service)


async def create_service(client: Client, property_id: str, data: dict) -> dict:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return {}

    slots = data.pop("slots", [])
    slug = await _ensure_unique_service_slug(client, property_id, data.get("name", "service"))
    row = {
        **data,
        "property_id": property_id,
        "account_id": account_id,
        "slug": slug,
        "updated_at": datetime.utcnow().isoformat(),
    }
    response = client.table("services").insert(row).execute()
    if not response.data:
        return {}
    service_id = response.data[0]["id"]
    await _replace_service_slots(client, service_id, slots)
    service = await get_service_by_id(client, property_id, service_id)
    return service or {}


async def update_service(
    client: Client,
    property_id: str,
    service_id: str,
    data: dict,
) -> dict | None:
    existing = await get_service_by_id(client, property_id, service_id)
    if not existing:
        return None

    slots = data.pop("slots", None)
    nullable_fields = {
        "category_id",
        "partner_id",
        "capacity_limit",
        "early_booking_discount_percent",
    }
    filtered = {
        k: v
        for k, v in data.items()
        if v is not None or k in nullable_fields
    }
    if "name" in filtered and filtered["name"] != existing.get("name"):
        filtered["slug"] = await _ensure_unique_service_slug(
            client,
            property_id,
            filtered["name"],
            exclude_service_id=service_id,
        )
    if filtered:
        filtered["updated_at"] = datetime.utcnow().isoformat()
        client.table("services").update(filtered).eq("id", service_id).eq(
            "property_id", property_id
        ).execute()

    if slots is not None:
        await _replace_service_slots(client, service_id, slots)

    return await get_service_by_id(client, property_id, service_id)


async def delete_service(client: Client, property_id: str, service_id: str) -> bool:
    response = (
        client.table("services")
        .delete()
        .eq("id", service_id)
        .eq("property_id", property_id)
        .execute()
    )
    return bool(response.data)


async def list_service_bookings(
    client: Client,
    property_id: str,
    service_id: str,
) -> list[dict]:
    response = (
        client.table("service_bookings")
        .select("*")
        .eq("property_id", property_id)
        .eq("service_id", service_id)
        .order("service_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    results = []
    for row in response.data or []:
        results.append(
            {
                **row,
                "quantity": _as_int(row.get("quantity"), 1),
                "total": _as_float(row.get("total")),
                "currency_code": (row.get("currency_code") or "USD").upper(),
            }
        )
    return results


async def get_service_analytics(client: Client, property_id: str) -> dict:
    revenue_response = (
        client.table("service_revenue_monthly")
        .select("month, revenue")
        .eq("property_id", property_id)
        .order("month")
        .execute()
    )
    revenue_by_month = []
    for row in revenue_response.data or []:
        raw_month = row.get("month")
        month_label = ""
        if isinstance(raw_month, str):
            try:
                month_label = datetime.strptime(raw_month, "%Y-%m-%d").strftime("%b")
            except ValueError:
                month_label = raw_month
        revenue_by_month.append(
            {
                "month": month_label,
                "revenue": _as_float(row.get("revenue")),
            }
        )

    services_response = (
        client.table("services")
        .select("id, name, image_urls, attach_rate, revenue_30d")
        .eq("property_id", property_id)
        .order("revenue_30d", desc=True)
        .execute()
    )
    services = services_response.data or []

    attach_rate_by_service = []
    for row in services:
        name = row.get("name") or ""
        compact_name = name.split(" ")[0] if name else "Service"
        attach_rate_by_service.append(
            {
                "name": compact_name,
                "rate": _as_float(row.get("attach_rate")),
            }
        )

    top_services = []
    for row in services[:5]:
        image_urls = row.get("image_urls") or []
        first_image = image_urls[0] if isinstance(image_urls, list) and image_urls else None
        top_services.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "image_url": first_image,
                "attach_rate": _as_float(row.get("attach_rate")),
                "revenue_30d": _as_float(row.get("revenue_30d")),
            }
        )

    return {
        "revenue_by_month": revenue_by_month,
        "attach_rate_by_service": attach_rate_by_service,
        "top_services": top_services,
    }
