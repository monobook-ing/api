from __future__ import annotations

from supabase import Client


async def get_properties_by_user(client: Client, user_id: str) -> list[dict]:
    """Get all properties for a user via their account memberships."""
    memberships = (
        client.table("team_members")
        .select("account_id")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not memberships.data:
        return []

    account_ids = [m["account_id"] for m in memberships.data]
    response = (
        client.table("properties")
        .select("*")
        .in_("account_id", account_ids)
        .execute()
    )
    return response.data or []


async def get_property_by_id(client: Client, property_id: str) -> dict | None:
    response = (
        client.table("properties")
        .select("*")
        .eq("id", property_id)
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def create_property(
    client: Client, user_id: str, data: dict
) -> dict:
    """Create a property under the user's existing account."""
    name = data.pop("name", "My Property")
    address = data.pop("address", None) or {}

    membership = (
        client.table("team_members")
        .select("account_id")
        .eq("user_id", user_id)
        .eq("status", "accepted")
        .is_("deleted_at", "null")
        .execute()
    )
    if not membership.data:
        membership = (
            client.table("team_members")
            .select("account_id")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .execute()
        )
    if not membership.data:
        raise ValueError("User is not a member of any account")
    account_id = membership.data[0]["account_id"]

    # Create property row
    prop_data = {
        "account_id": account_id,
        "name": name,
        **address,
        **{k: v for k, v in data.items() if v is not None},
    }
    prop = client.table("properties").insert(prop_data).execute()
    return prop.data[0]


async def update_property(
    client: Client, property_id: str, data: dict
) -> dict | None:
    address = data.pop("address", None)

    update_fields: dict = {}
    if address:
        update_fields.update({k: v for k, v in address.items() if v is not None})
    update_fields.update({k: v for k, v in data.items() if v is not None})

    if update_fields:
        client.table("properties").update(update_fields).eq("id", property_id).execute()

    return await get_property_by_id(client, property_id)


async def delete_property(client: Client, property_id: str) -> bool:
    prop = (
        client.table("properties").select("id").eq("id", property_id).execute()
    )
    if not prop.data:
        return False
    client.table("properties").delete().eq("id", property_id).execute()
    return True


async def user_owns_property(client: Client, user_id: str, property_id: str) -> bool:
    """Check if user has access to this property via team membership."""
    prop = (
        client.table("properties").select("account_id").eq("id", property_id).execute()
    )
    if not prop.data:
        return False
    account_id = prop.data[0]["account_id"]
    membership = (
        client.table("team_members")
        .select("id")
        .eq("account_id", account_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return bool(membership.data)
