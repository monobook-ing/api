from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.api import deps
from app.crud.team_member import (
    check_team_member_exists,
    create_team_member,
    get_team_member_details,
    get_team_member_by_id,
    get_team_members_by_account,
    get_user_default_account_id,
    soft_delete_team_member,
    update_team_member,
)
from app.crud.user import create_invited_user, get_user_by_email
from app.crud.magic_token import create_magic_token
from app.db.base import get_supabase
from app.schemas.team_member import (
    TeamMemberInvite,
    TeamMemberListResponse,
    TeamMemberResponse,
    TeamMemberUpdate,
)
from app.services.resend import (
    ResendConfigurationError,
    ResendSendError,
    send_magic_link_email,
)

router = APIRouter(prefix="/v1.0/team_members", tags=["team_members"])


@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_team_member(
    payload: TeamMemberInvite,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> dict:
    """Invite a new team member to the current user's default account."""
    # Get inviter's default account
    account_id = await get_user_default_account_id(client, current_user["id"])
    
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default account found for current user"
        )
    
    # Check if user with email exists
    invited_user = await get_user_by_email(client, payload.email)
    
    # If user exists, check if already a team member
    if invited_user:
        existing_member = await check_team_member_exists(
            client, account_id, invited_user["id"]
        )
        if existing_member:
            if existing_member.get("status") == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User has already rejected an invitation",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a team member"
            )
        
        # Add existing user as team member
        await create_team_member(
            client,
            account_id=account_id,
            user_id=invited_user["id"],
            inviter_id=current_user["id"],
            role=payload.role,
            status="invited",
        )
    else:
        # User doesn't exist, create user and send magic link for sign-up
        invited_user = await create_invited_user(client, payload.email)

        token = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        await create_magic_token(
            client,
            email=payload.email,
            token=token,
            expires_at=expires_at,
            user_id=invited_user["id"]
        )

        await create_team_member(
            client,
            account_id=account_id,
            user_id=invited_user["id"],
            inviter_id=current_user["id"],
            role=payload.role,
            status="invited",
        )
        
        # Send invitation email with magic link
        try:
            await send_magic_link_email(
                recipient=payload.email,
                token=token,
                expires_at=expires_at
            )
        except (ResendConfigurationError, ResendSendError) as exc:
            # Log error but don't fail the invitation
            # In production, you might want to queue this for retry
            pass
    
    return {
        "message": "Invitation sent successfully",
        "email": payload.email,
        "user_exists": invited_user is not None,
        "status": "invited",
    }


@router.get("", response_model=TeamMemberListResponse)
async def list_team_members(
    statuses: list[str] | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return"),
    cursor: str | None = Query(None, description="Pagination cursor for infinite scroll"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> TeamMemberListResponse:
    """List all team members in the current user's default account."""
    allowed_statuses = {"invited", "accepted", "rejected"}
    if statuses:
        normalized_statuses = [value.lower() for value in statuses]
        if any(value not in allowed_statuses for value in normalized_statuses):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status value",
            )
        statuses = normalized_statuses

    # Get current user's default account
    account_id = await get_user_default_account_id(client, current_user["id"])
    
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default account found for current user"
        )
    
    try:
        result = await get_team_members_by_account(
            client,
            account_id,
            statuses=statuses,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return TeamMemberListResponse(
        items=[TeamMemberResponse(**member) for member in result["items"]],
        next_cursor=result["next_cursor"],
    )


@router.get("/{member_id}", response_model=TeamMemberResponse)
async def get_team_member(
    member_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> TeamMemberResponse:
    """Get a specific team member by ID in the current user's default account."""
    member = await get_team_member_details(client, member_id)

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )

    account_id = await get_user_default_account_id(client, current_user["id"])

    if not account_id or member["account_id"] != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this team member"
        )

    return TeamMemberResponse(
        id=member["id"],
        role=member["role"],
        status=member["status"],
        user_id=member["user_id"],
        first_name=member.get("first_name"),
        last_name=member.get("last_name"),
        name=member["name"],
        joined_at=member["joined_at"],
    )


@router.patch("/{member_id}", status_code=status.HTTP_200_OK)
async def update_team_member_role(
    member_id: str,
    payload: TeamMemberUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> dict:
    """Update a team member's role or status."""
    allowed_roles = {"admin", "owner", "guest"}
    # Check if team member exists
    member = await get_team_member_by_id(client, member_id)
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )
    
    # Get current user's default account to verify authorization
    account_id = await get_user_default_account_id(client, current_user["id"])
    
    if not account_id or member["account_id"] != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this team member"
        )

    # Prevent updating the account owner
    if member["role"].lower() == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update the account owner"
        )
    
    # Prepare update data
    update_data = {}
    if payload.role is not None:
        normalized_role = payload.role.lower()
        if normalized_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role value"
            )
        update_data["role"] = normalized_role
    if payload.status is not None:
        allowed_statuses = {"invited", "accepted", "rejected"}
        normalized_status = payload.status.lower()
        if normalized_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status value"
            )
        update_data["status"] = normalized_status
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided"
        )
    
    # Update team member
    try:
        updated_member = await update_team_member(client, member_id, update_data)
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid update data"
        ) from exc
    
    if not updated_member:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team member"
        )
    
    return {
        "message": "Team member updated successfully",
        "id": member_id,
        "role": updated_member.get("role"),
        "status": updated_member.get("status"),
    }


@router.delete("/{member_id}", status_code=status.HTTP_200_OK)
async def remove_team_member(
    member_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> dict:
    """Remove a team member from the account (soft delete)."""
    # Check if team member exists
    member = await get_team_member_by_id(client, member_id)
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )
    
    # Get current user's default account to verify authorization
    account_id = await get_user_default_account_id(client, current_user["id"])
    
    if not account_id or member["account_id"] != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to remove this team member"
        )

    # Prevent removing any account owner
    if member["role"].lower() == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the account owner"
        )

    # Prevent removing yourself if you're the owner
    if member["user_id"] == current_user["id"] and member["role"] == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself as the account owner"
        )
    
    # Soft delete the team member
    deleted = await soft_delete_team_member(
        client, member_id, current_user["id"]
    )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove team member"
        )
    
    return {
        "message": "Team member removed successfully",
        "id": member_id
    }
