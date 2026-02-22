from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.property import user_owns_property
from app.crud.settings import get_connections, get_dashboard_metrics, upsert_connection
from app.db.base import get_supabase
from app.schemas.settings import (
    ConnectionListResponse,
    ConnectionResponse,
    ConnectionToggle,
    DashboardMetricsResponse,
)

router = APIRouter(prefix="/v1.0/properties/{property_id}", tags=["settings"])


async def _check_access(client: Client, user_id: str, property_id: str):
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# -- PMS connections --

@router.get("/pms-connections", response_model=ConnectionListResponse)
async def list_pms_connections(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    rows = await get_connections(client, property_id, "pms_connections")
    return ConnectionListResponse(items=rows)


@router.put("/pms-connections/{provider}", response_model=ConnectionResponse)
async def toggle_pms_connection(
    property_id: str,
    provider: str,
    payload: ConnectionToggle,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    row = await upsert_connection(client, property_id, "pms_connections", provider, payload.enabled)
    return row


# -- Payment connections --

@router.get("/payment-connections", response_model=ConnectionListResponse)
async def list_payment_connections(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    rows = await get_connections(client, property_id, "payment_connections")
    return ConnectionListResponse(items=rows)


@router.put("/payment-connections/{provider}", response_model=ConnectionResponse)
async def toggle_payment_connection(
    property_id: str,
    provider: str,
    payload: ConnectionToggle,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    row = await upsert_connection(client, property_id, "payment_connections", provider, payload.enabled)
    return row


# -- Dashboard metrics --

@router.get("/metrics", response_model=DashboardMetricsResponse)
async def get_metrics(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get dashboard metrics (last 12 data points) for a property."""
    await _check_access(client, current_user["id"], property_id)
    rows = await get_dashboard_metrics(client, property_id, limit=12)

    if not rows:
        return DashboardMetricsResponse()

    latest = rows[-1]
    return DashboardMetricsResponse(
        ai_direct_bookings=latest.get("ai_direct_bookings", 0),
        commission_saved=float(latest.get("commission_saved", 0)),
        occupancy_rate=float(latest.get("occupancy_rate", 0)),
        revenue=float(latest.get("revenue", 0)),
        ai_direct_bookings_trend=[r["ai_direct_bookings"] for r in rows],
        commission_saved_trend=[float(r["commission_saved"]) for r in rows],
        occupancy_trend=[float(r["occupancy_rate"]) for r in rows],
        revenue_trend=[float(r["revenue"]) for r in rows],
    )
