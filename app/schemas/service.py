from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ServiceCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    icon: str = Field("📦", min_length=1, max_length=16)
    sort_order: int = 0


class ServiceCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    icon: str | None = Field(default=None, min_length=1, max_length=16)
    sort_order: int | None = None


class ServiceCategoryReorderItem(BaseModel):
    id: str
    sort_order: int = Field(..., ge=0)


class ServiceCategoryReorder(BaseModel):
    items: list[ServiceCategoryReorderItem] = Field(default_factory=list)


class ServiceCategoryResponse(BaseModel):
    id: str
    account_id: str
    slug: str
    name: str
    description: str
    icon: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ServiceCategoryListResponse(BaseModel):
    items: list[ServiceCategoryResponse]


class ServicePartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    revenue_share_percent: float = Field(0, ge=0, le=100)
    payout_type: str = "manual"
    external_url: str | None = None
    attribution_tracking: bool = False
    status: str = "active"


class ServicePartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    revenue_share_percent: float | None = Field(default=None, ge=0, le=100)
    payout_type: str | None = None
    external_url: str | None = None
    attribution_tracking: bool | None = None
    status: str | None = None


class ServicePartnerResponse(BaseModel):
    id: str
    account_id: str
    slug: str
    name: str
    revenue_share_percent: float
    payout_type: str
    external_url: str | None = None
    attribution_tracking: bool
    status: str
    active_services: int = 0
    revenue_generated: float = 0
    created_at: datetime
    updated_at: datetime


class ServicePartnerListResponse(BaseModel):
    items: list[ServicePartnerResponse]


class ServiceSlotCreate(BaseModel):
    time: str = Field(..., min_length=4, max_length=8)
    capacity: int = Field(0, ge=0)
    booked: int = Field(0, ge=0)
    sort_order: int = Field(0, ge=0)


class ServiceSlotResponse(BaseModel):
    id: str
    service_id: str
    time: str
    capacity: int
    booked: int
    sort_order: int
    created_at: datetime


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    short_description: str = ""
    full_description: str = ""
    image_urls: list[str] = Field(default_factory=list)
    type: str = "internal"
    category_id: str | None = None
    partner_id: str | None = None
    status: str = "draft"
    visibility: str = "public"
    pricing_type: str = "fixed"
    price: float = Field(0, ge=0)
    currency_code: str = Field("USD", min_length=3, max_length=3)
    vat_percent: float = Field(0, ge=0, le=100)
    allow_discount: bool = False
    bundle_eligible: bool = False
    availability_type: str = "always"
    capacity_mode: str = "unlimited"
    capacity_limit: int | None = Field(default=None, ge=0)
    recurring_schedule_enabled: bool = False
    available_before_booking: bool = True
    available_during_booking: bool = True
    post_booking_upsell: bool = False
    in_stay_qr_ordering: bool = False
    upsell_trigger_room_type: str = "any"
    early_booking_discount_percent: float | None = Field(default=None, ge=0, le=100)
    knowledge_language: str = "en"
    knowledge_ai_search_enabled: bool = True
    attach_rate: float = Field(0, ge=0)
    total_bookings: int = Field(0, ge=0)
    revenue_30d: float = Field(0, ge=0)
    conversion_rate: float = Field(0, ge=0)
    slots: list[ServiceSlotCreate] = Field(default_factory=list)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    short_description: str | None = None
    full_description: str | None = None
    image_urls: list[str] | None = None
    type: str | None = None
    category_id: str | None = None
    partner_id: str | None = None
    status: str | None = None
    visibility: str | None = None
    pricing_type: str | None = None
    price: float | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    vat_percent: float | None = Field(default=None, ge=0, le=100)
    allow_discount: bool | None = None
    bundle_eligible: bool | None = None
    availability_type: str | None = None
    capacity_mode: str | None = None
    capacity_limit: int | None = Field(default=None, ge=0)
    recurring_schedule_enabled: bool | None = None
    available_before_booking: bool | None = None
    available_during_booking: bool | None = None
    post_booking_upsell: bool | None = None
    in_stay_qr_ordering: bool | None = None
    upsell_trigger_room_type: str | None = None
    early_booking_discount_percent: float | None = Field(default=None, ge=0, le=100)
    knowledge_language: str | None = None
    knowledge_ai_search_enabled: bool | None = None
    attach_rate: float | None = Field(default=None, ge=0)
    total_bookings: int | None = Field(default=None, ge=0)
    revenue_30d: float | None = Field(default=None, ge=0)
    conversion_rate: float | None = Field(default=None, ge=0)
    slots: list[ServiceSlotCreate] | None = None


class ServiceResponse(BaseModel):
    id: str
    property_id: str
    account_id: str
    category_id: str | None = None
    partner_id: str | None = None
    slug: str
    name: str
    short_description: str
    full_description: str
    image_urls: list[str]
    type: str
    status: str
    visibility: str
    pricing_type: str
    price: float
    currency_code: str
    vat_percent: float
    allow_discount: bool
    bundle_eligible: bool
    availability_type: str
    capacity_mode: str
    capacity_limit: int | None = None
    recurring_schedule_enabled: bool
    available_before_booking: bool
    available_during_booking: bool
    post_booking_upsell: bool
    in_stay_qr_ordering: bool
    upsell_trigger_room_type: str
    early_booking_discount_percent: float | None = None
    knowledge_language: str
    knowledge_ai_search_enabled: bool
    attach_rate: float
    total_bookings: int
    revenue_30d: float
    conversion_rate: float
    category_name: str | None = None
    partner_name: str | None = None
    slots: list[ServiceSlotResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ServiceListResponse(BaseModel):
    items: list[ServiceResponse]


class ServiceBookingResponse(BaseModel):
    id: str
    property_id: str
    service_id: str
    booking_id: str | None = None
    external_ref: str
    guest_name: str
    service_date: date
    quantity: int
    total: float
    currency_code: str
    status: str
    created_at: datetime
    updated_at: datetime


class ServiceBookingListResponse(BaseModel):
    items: list[ServiceBookingResponse]


class ServiceRevenuePoint(BaseModel):
    month: str
    revenue: float


class ServiceAttachRatePoint(BaseModel):
    name: str
    rate: float


class ServiceTopPerformer(BaseModel):
    id: str
    name: str
    image_url: str | None = None
    attach_rate: float
    revenue_30d: float


class ServiceAnalyticsResponse(BaseModel):
    revenue_by_month: list[ServiceRevenuePoint]
    attach_rate_by_service: list[ServiceAttachRatePoint]
    top_services: list[ServiceTopPerformer]

