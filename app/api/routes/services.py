from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.property import user_owns_property
from app.crud.service import (
    create_service,
    create_service_category,
    create_service_partner,
    delete_service,
    delete_service_category,
    get_service_analytics,
    get_service_by_id,
    list_service_bookings,
    list_service_categories,
    list_service_partners,
    list_services,
    reorder_service_categories,
    update_service,
    update_service_category,
    update_service_partner,
)
from app.db.base import get_supabase
from app.schemas.service import (
    ServiceAnalyticsResponse,
    ServiceBookingListResponse,
    ServiceCategoryCreate,
    ServiceCategoryListResponse,
    ServiceCategoryReorder,
    ServiceCategoryResponse,
    ServiceCategoryUpdate,
    ServiceCreate,
    ServiceListResponse,
    ServicePartnerCreate,
    ServicePartnerListResponse,
    ServicePartnerResponse,
    ServicePartnerUpdate,
    ServiceResponse,
    ServiceUpdate,
)

router = APIRouter(prefix="/v1.0/properties/{property_id}/services", tags=["services"])


async def _check_access(client: Client, user_id: str, property_id: str) -> None:
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("/categories", response_model=ServiceCategoryListResponse)
async def get_categories(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    items = await list_service_categories(client, property_id)
    return ServiceCategoryListResponse(items=items)


@router.post(
    "/categories",
    response_model=ServiceCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    property_id: str,
    payload: ServiceCategoryCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    created = await create_service_category(client, property_id, payload.model_dump())
    return created


@router.put("/categories/reorder", response_model=ServiceCategoryListResponse)
async def put_category_order(
    property_id: str,
    payload: ServiceCategoryReorder,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    items = await reorder_service_categories(
        client, property_id, [item.model_dump() for item in payload.items]
    )
    return ServiceCategoryListResponse(items=items)


@router.patch("/categories/{category_id}", response_model=ServiceCategoryResponse)
async def patch_category(
    property_id: str,
    category_id: str,
    payload: ServiceCategoryUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    updated = await update_service_category(
        client, property_id, category_id, payload.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return updated


@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK)
async def remove_category(
    property_id: str,
    category_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    deleted = await delete_service_category(client, property_id, category_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return {"message": "Category deleted", "id": category_id}


@router.get("/partners", response_model=ServicePartnerListResponse)
async def get_partners(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    items = await list_service_partners(client, property_id)
    return ServicePartnerListResponse(items=items)


@router.post(
    "/partners",
    response_model=ServicePartnerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_partner(
    property_id: str,
    payload: ServicePartnerCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    created = await create_service_partner(client, property_id, payload.model_dump())
    items = await list_service_partners(client, property_id)
    for item in items:
        if item["id"] == created.get("id"):
            return item
    return created


@router.patch("/partners/{partner_id}", response_model=ServicePartnerResponse)
async def patch_partner(
    property_id: str,
    partner_id: str,
    payload: ServicePartnerUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    updated = await update_service_partner(
        client, property_id, partner_id, payload.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    items = await list_service_partners(client, property_id)
    for item in items:
        if item["id"] == partner_id:
            return item
    return updated


@router.get("/analytics", response_model=ServiceAnalyticsResponse)
async def get_analytics(
    property_id: str,
    range_key: str | None = Query(default=None, alias="range"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    # `range` is accepted for UI compatibility; currently snapshots are served as stored.
    _ = range_key
    await _check_access(client, current_user["id"], property_id)
    analytics = await get_service_analytics(client, property_id)
    return ServiceAnalyticsResponse(**analytics)


@router.get("", response_model=ServiceListResponse)
async def get_services(
    property_id: str,
    search: str | None = Query(default=None),
    type_filter: str | None = Query(default=None, alias="type"),
    category_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    items = await list_services(
        client,
        property_id,
        search=search,
        type_filter=type_filter,
        category_id=category_id,
        status_filter=status_filter,
    )
    return ServiceListResponse(items=items)


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_service(
    property_id: str,
    payload: ServiceCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    created = await create_service(client, property_id, payload.model_dump())
    return created


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_single_service(
    property_id: str,
    service_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    service = await get_service_by_id(client, property_id, service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_existing_service(
    property_id: str,
    service_id: str,
    payload: ServiceUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    updated = await update_service(
        client, property_id, service_id, payload.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return updated


@router.delete("/{service_id}", status_code=status.HTTP_200_OK)
async def delete_existing_service(
    property_id: str,
    service_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    deleted = await delete_service(client, property_id, service_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return {"message": "Service deleted", "id": service_id}


@router.get("/{service_id}/bookings", response_model=ServiceBookingListResponse)
async def get_service_booking_rows(
    property_id: str,
    service_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    service = await get_service_by_id(client, property_id, service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    items = await list_service_bookings(client, property_id, service_id)
    return ServiceBookingListResponse(items=items)
