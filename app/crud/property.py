from __future__ import annotations

from supabase import Client


async def get_properties_by_user(client: Client, user_id: str) -> list[dict]:
    """Get all properties for a user via their account memberships."""
    # Get accounts the user belongs to
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
        .select("*, accounts!inner(name, is_default)")
        .in_("account_id", account_ids)
        .execute()
    )
    # Flatten account name into property response
    results = []
    for row in response.data or []:
        acct = row.pop("accounts", {})
        row["name"] = acct.get("name", row.get("name", ""))
        results.append(row)
    return results


async def get_property_by_id(client: Client, property_id: str) -> dict | None:
    response = (
        client.table("properties")
        .select("*, accounts!inner(name, is_default)")
        .eq("id", property_id)
        .execute()
    )
    if response.data and len(response.data) > 0:
        row = response.data[0]
        acct = row.pop("accounts", {})
        row["name"] = acct.get("name", row.get("name", ""))
        return row
    return None


async def create_property(
    client: Client, user_id: str, data: dict
) -> dict:
    """Create an account + property pair. Returns the property row."""
    name = data.pop("name", "My Property")
    address = data.pop("address", None) or {}

    # Create account (account = property)
    acct = (
        client.table("accounts")
        .insert({"name": name, "is_default": False, "created_by": user_id})
        .execute()
    )
    account_id = acct.data[0]["id"]

    # Link user as admin
    client.table("team_members").insert(
        {"account_id": account_id, "user_id": user_id, "role": "admin", "status": "accepted"}
    ).execute()

    # Create property row
    prop_data = {
        "account_id": account_id,
        **address,
        **{k: v for k, v in data.items() if v is not None},
    }
    prop = client.table("properties").insert(prop_data).execute()
    row = prop.data[0]
    row["name"] = name
    return row


async def update_property(
    client: Client, property_id: str, data: dict
) -> dict | None:
    address = data.pop("address", None)
    name = data.pop("name", None)

    update_fields: dict = {}
    if address:
        update_fields.update({k: v for k, v in address.items() if v is not None})
    update_fields.update({k: v for k, v in data.items() if v is not None})

    if update_fields:
        client.table("properties").update(update_fields).eq("id", property_id).execute()

    if name is not None:
        # Also update the account name
        prop = (
            client.table("properties").select("account_id").eq("id", property_id).execute()
        )
        if prop.data:
            client.table("accounts").update({"name": name}).eq("id", prop.data[0]["account_id"]).execute()

    return await get_property_by_id(client, property_id)


async def delete_property(client: Client, property_id: str) -> bool:
    prop = (
        client.table("properties").select("account_id").eq("id", property_id).execute()
    )
    if not prop.data:
        return False
    account_id = prop.data[0]["account_id"]
    # Cascade: deleting account cascades to property, rooms, bookings, etc.
    client.table("accounts").delete().eq("id", account_id).execute()
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
