import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from typing import Any

from supabase import Client


def _encode_cursor(created_at: str | datetime, member_id: str) -> str:
    """Encode pagination cursor payload.

    The cursor stores the last item's creation timestamp and ID so we can
    continue pagination deterministically even when multiple rows share the
    same timestamp.
    """

    created_at_value = (
        created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
    )

    payload = {"created_at": created_at_value, "id": member_id}
    raw = json.dumps(payload).encode("utf-8")
    return urlsafe_b64encode(raw).decode("utf-8")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a pagination cursor string.

    Raises:
        ValueError: If the cursor cannot be decoded or is missing expected
            fields.
    """

    try:
        raw = urlsafe_b64decode(cursor).decode("utf-8")
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - intentional broad catch for decoding errors
        raise ValueError("Invalid pagination cursor") from exc

    if not isinstance(payload, dict) or not {"created_at", "id"}.issubset(payload):
        raise ValueError("Invalid pagination cursor")

    return payload


async def get_user_default_account_id(client: Client, user_id: str) -> str | None:
    """Get the default account ID for a user.

    Falls back to the first active team membership if the user doesn't own a
    default account. This matches the logic used by the `/users/me` endpoint.
    """
    response = (
        client.table("accounts")
        .select("id")
        .eq("created_by", user_id)
        .eq("is_default", True)
        .limit(1)
        .execute()
    )
    
    if response.data and len(response.data) > 0:
        return response.data[0]["id"]

    team_member_response = (
        client.table("team_members")
        .select("account_id")
        .eq("user_id", user_id)
        .eq("status", "accepted")
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if team_member_response.data and len(team_member_response.data) > 0:
        return team_member_response.data[0]["account_id"]
    return None


async def get_team_members_by_account(
    client: Client,
    account_id: str,
    *,
    statuses: list[str] | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    """Get team members for an account with optional filtering and pagination."""
    # Use the specific foreign key relationship to avoid ambiguity
    query = (
        client.table("team_members")
        .select(
            "id, role, status, user_id, created_at, users!team_members_user_id_fkey(first_name, last_name)"
        )
        .eq("account_id", account_id)
        .is_("deleted_at", "null")
    )

    if statuses:
        normalized_statuses = [status.lower() for status in statuses]
        query = query.in_("status", normalized_statuses)

    if cursor:
        payload = _decode_cursor(cursor)
        created_at = str(payload["created_at"])
        member_id = str(payload["id"])
        condition = (
            f"and(created_at.eq.{created_at},id.lt.{member_id}),created_at.lt.{created_at}"
        )
        query = query.or_(condition)

    query = query.order("created_at", desc=True).order("id", desc=True).limit(limit + 1)

    response = query.execute()

    members = []
    for member in response.data[:limit]:
        user_name = None
        if member.get("users") and isinstance(member["users"], dict):
            # Combine first and last name if available
            first_name = member["users"].get("first_name") or ""
            last_name = member["users"].get("last_name") or ""
            user_name = f"{first_name} {last_name}".strip() or None

        members.append(
            {
                "id": member["id"],
                "role": member["role"],
                "status": member["status"],
                "user_id": member["user_id"],
                "name": user_name,
                "joined_at": member["created_at"],
            }
        )

    next_cursor = None
    if len(response.data) > limit:
        last_item = response.data[limit - 1]
        next_cursor = _encode_cursor(last_item["created_at"], last_item["id"])

    return {"items": members, "next_cursor": next_cursor}


async def check_team_member_exists(client: Client, account_id: str, user_id: str) -> dict | None:
    """Check if a team member already exists."""
    response = (
        client.table("team_members")
        .select("*")
        .eq("account_id", account_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def create_team_member(
    client: Client,
    account_id: str,
    user_id: str,
    inviter_id: str,
    role: str = "admin",
    status: str = "accepted",
) -> dict:
    """Create a new team member."""
    normalized_status = status.lower() if isinstance(status, str) else status
    member_data = {
        "account_id": account_id,
        "user_id": user_id,
        "role": role,
        "status": normalized_status,
        "created_by": inviter_id
    }
    
    response = client.table("team_members").insert(member_data).execute()
    
    if not response.data or len(response.data) == 0:
        raise ValueError("Failed to create team member")
    
    return response.data[0]


async def get_team_member_by_id(client: Client, member_id: str) -> dict | None:
    """Get a team member by ID."""
    response = (
        client.table("team_members")
        .select("*")
        .eq("id", member_id)
        .is_("deleted_at", "null")
        .execute()
    )
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def get_team_member_details(
    client: Client,
    member_id: str,
) -> dict | None:
    """Get a team member with user details by ID."""
    response = (
        client.table("team_members")
        .select("id, role, status, user_id, account_id, created_at, users!team_members_user_id_fkey(first_name, last_name)")
        .eq("id", member_id)
        .is_("deleted_at", "null")
        .execute()
    )

    if not response.data:
        return None

    member = response.data[0]
    first_name = None
    last_name = None
    user_name = None
    if member.get("users") and isinstance(member["users"], dict):
        first_name = member["users"].get("first_name") or None
        last_name = member["users"].get("last_name") or None
        if first_name:
            user_name = first_name

    return {
        "id": member["id"],
        "role": member["role"],
        "status": member["status"],
        "user_id": member["user_id"],
        "account_id": member["account_id"],
        "first_name": first_name,
        "last_name": last_name,
        "name": user_name,
        "joined_at": member["created_at"],
    }


async def update_team_member(
    client: Client,
    member_id: str,
    update_data: dict
) -> dict | None:
    """Update a team member."""
    if not update_data:
        return None

    response = (
        client.table("team_members")
        .update(update_data)
        .eq("id", member_id)
        .is_("deleted_at", "null")
        .execute()
    )
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def soft_delete_team_member(
    client: Client,
    member_id: str,
    deleted_by: str
) -> bool:
    """Soft delete a team member."""
    from datetime import datetime, timezone
    
    update_data = {
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by": deleted_by
    }
    
    response = (
        client.table("team_members")
        .update(update_data)
        .eq("id", member_id)
        .is_("deleted_at", "null")
        .execute()
    )
    
    return response.data and len(response.data) > 0
