from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from postgrest.exceptions import APIError

from app.crud.magic_token import create_magic_token, get_magic_token_by_token, delete_magic_token
from app.crud.notification import create_notification, get_user_notification_by_subject
from app.crud.user import get_user_by_email
from app.db.base import get_supabase
from app.services.resend import (
    ResendConfigurationError,
    ResendSendError,
    send_invite_accepted_email,
    send_magic_link_email,
    send_welcome_email,
)
from app.schemas.magic_link import MagicLinkRequest, MagicLinkResponse, MagicLinkConfirm
from app.schemas.notification import NotificationType
from app.core.security import create_access_token
from app.core.config import get_settings

MAGIC_LINK_EXPIRY_MINUTES = 15
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1.0", tags=["signin"])


@router.post("/signin", response_model=MagicLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_magic_link(
    payload: MagicLinkRequest, 
    client: Client = Depends(get_supabase)
) -> MagicLinkResponse:
    """Create a magic link for passwordless authentication."""
    try:
        user = await get_user_by_email(client, payload.email)

        token = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)

        # This will now delete any existing tokens for the email before creating a new one
        await create_magic_token(
            client,
            email=payload.email,
            token=token,
            expires_at=expires_at,
            user_id=user["id"] if user else None,
        )

        try:
            await send_magic_link_email(
                recipient=payload.email, 
                token=token, 
                expires_at=expires_at
            )
        except ResendConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ResendSendError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        return MagicLinkResponse(token=token, expires_at=expires_at)
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except APIError as exc:
        # Handle Supabase/PostgREST errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc.message if hasattr(exc, 'message') else str(exc)}"
        ) from exc
    except Exception as exc:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating magic link"
        ) from exc


@router.post("/signin/confirm", status_code=status.HTTP_200_OK)
async def confirm_magic_link(
    payload: MagicLinkConfirm,
    client: Client = Depends(get_supabase),
) -> dict:
    """Confirm a magic link, authenticate the user, and bootstrap their account on first sign-in."""
    try:
        settings = get_settings()
        welcome_subject = f"Welcome to {settings.app_name}!"
        membership_status: str | None = None
        # Get the magic token
        magic_token = await get_magic_token_by_token(client, payload.token)
        
        if not magic_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired magic link"
            )
        
        # Check if token has been used
        if magic_token.get("used_at"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This magic link has already been used"
            )

        # Ensure the token belongs to the provided email
        token_email = magic_token["email"]
        if token_email.lower() != payload.email.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token does not match the provided email"
            )
        
        # Check if token has expired
        expires_at = datetime.fromisoformat(magic_token["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires_at:
            # Clean up expired token
            await delete_magic_token(client, payload.token)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This magic link has expired"
            )
        
        email = token_email
        
        # Check if user exists
        user = await get_user_by_email(client, email)
        
        # If user doesn't exist, create new user with account and team member
        new_user_created = False
        if not user:
            # Extract name from email (part before @)
            name = email.split("@")[0]
            
            # Create user
            user_data = {
                "email": email,
                "first_name": name,
            }
            user_response = client.table("users").insert(user_data).execute()
            
            if not user_response.data or len(user_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user"
                )
            
            user = user_response.data[0]
            user_id = user["id"]
            
            # Create default account
            account_data = {
                "name": f"{name}'s Account",
                "is_default": True,
                "created_by": user_id,
                "updated_by": user_id,
            }
            account_response = client.table("accounts").insert(account_data).execute()
            
            if not account_response.data or len(account_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create account"
                )
            
            account = account_response.data[0]
            account_id = account["id"]
            
            # Create team member with admin role
            team_member_data = {
                "account_id": account_id,
                "user_id": user_id,
                "role": "admin",
                "status": "accepted",
                "created_by": user_id,
            }
            team_member_response = client.table("team_members").insert(team_member_data).execute()
            
            if not team_member_response.data or len(team_member_response.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create team member"
                )
            
            new_user_created = True
            membership_status = "accepted"
        
        if new_user_created:
            subject = welcome_subject
            body = (
                f"Thanks for joining {settings.app_name}! "
                "We're glad you're here."
            )

            await create_notification(
                client,
                user_id=user["id"],
                subject=subject,
                body=body,
                notification_type=NotificationType.WELCOME,
                details=body,
                cta=None,
            )

            try:
                await send_welcome_email(
                    recipient=email,
                    first_name=user.get("first_name"),
                )
            except ResendConfigurationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            except ResendSendError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(exc),
                ) from exc
        else:
            existing_welcome_notification = await get_user_notification_by_subject(
                client, user_id=user["id"], subject=welcome_subject
            )
            if not existing_welcome_notification:
                body = (
                    f"Thanks for joining {settings.app_name}! "
                    "We're glad you're here."
                )

                await create_notification(
                    client,
                    user_id=user["id"],
                    subject=welcome_subject,
                    body=body,
                    notification_type=NotificationType.WELCOME,
                    details=body,
                    cta=None,
                )

                try:
                    await send_welcome_email(
                        recipient=email,
                        first_name=user.get("first_name"),
                    )
                except ResendConfigurationError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=str(exc),
                    ) from exc
                except ResendSendError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=str(exc),
                    ) from exc
            invited_memberships = (
                client.table("team_members")
                .select("id, status, created_by, account_id")
                .eq("user_id", user["id"])
                .is_("deleted_at", "null")
                .execute()
            )

            has_invited_membership = False
            has_rejected_membership = False

            if invited_memberships.data:
                for membership in invited_memberships.data:
                    status_value = membership.get("status")
                    if status_value == "invited":
                        has_invited_membership = True
                    if status_value == "rejected":
                        has_rejected_membership = True

            if has_invited_membership:
                accepted_invites = [
                    membership
                    for membership in invited_memberships.data
                    if membership.get("status") == "invited"
                ]
                (
                    client.table("team_members")
                    .update({"status": "accepted"})
                    .eq("user_id", user["id"])
                    .eq("status", "invited")
                    .is_("deleted_at", "null")
                    .execute()
                )
                for membership in accepted_invites:
                    inviter_id = membership.get("created_by")
                    account_id = membership.get("account_id")
                    if not inviter_id:
                        continue

                    inviter_response = (
                        client.table("users")
                        .select("email, first_name, last_name")
                        .eq("id", inviter_id)
                        .limit(1)
                        .execute()
                    )
                    inviter = inviter_response.data[0] if inviter_response.data else None
                    if not inviter or not inviter.get("email"):
                        continue

                    account_name = None
                    if account_id:
                        account_response = (
                            client.table("accounts")
                            .select("name")
                            .eq("id", account_id)
                            .limit(1)
                            .execute()
                        )
                        if account_response.data:
                            account_name = account_response.data[0].get("name")

                    inviter_name_parts = [
                        inviter.get("first_name") or "",
                        inviter.get("last_name") or "",
                    ]
                    inviter_name = (
                        " ".join([part for part in inviter_name_parts if part]).strip() or None
                    )
                    invitee_display = user.get("first_name") or user["email"].split("@")[0]
                    account_display = account_name or "the account"

                    subject = f"{invitee_display} accepted your invitation to {settings.app_name}"
                    body = (
                        f"{invitee_display} ({user['email']}) accepted your invitation to join "
                        f"{account_display} on {settings.app_name}."
                    )

                    await create_notification(
                        client,
                        user_id=inviter_id,
                        subject=subject,
                        body=body,
                        notification_type=NotificationType.INVITE_ACCEPTED,
                        details=body,
                        cta=None,
                    )
                    try:
                        await send_invite_accepted_email(
                            recipient=inviter["email"],
                            inviter_name=inviter_name,
                            invitee_name=user.get("first_name"),
                            invitee_email=user["email"],
                            account_name=account_name,
                        )
                    except (ResendConfigurationError, ResendSendError) as exc:
                        logger.warning("Failed to send invite acceptance email: %s", exc)
                membership_status = "accepted"
            elif has_rejected_membership:
                membership_status = "rejected"
        
        # Delete the magic token after successful confirmation
        await delete_magic_token(client, payload.token)
        
        # Create JWT access token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": user["email"], "user_id": user["id"]}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user.get("first_name"),
                "team_member_status": membership_status,
            }
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except APIError as exc:
        # Handle Supabase/PostgREST errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc.message if hasattr(exc, 'message') else str(exc)}"
        ) from exc
    except Exception as exc:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during authentication"
        ) from exc
