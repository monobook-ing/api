from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ConnectionToggle(BaseModel):
    enabled: bool


class ConnectionResponse(BaseModel):
    id: str
    property_id: str
    provider: str
    enabled: bool
    config: dict = {}
    created_at: datetime
    updated_at: datetime


class ConnectionListResponse(BaseModel):
    items: list[ConnectionResponse]


class DashboardMetricsResponse(BaseModel):
    ai_direct_bookings: int = 0
    commission_saved: float = 0
    occupancy_rate: float = 0
    revenue: float = 0
    ai_direct_bookings_trend: list[int] = []
    commission_saved_trend: list[float] = []
    occupancy_trend: list[float] = []
    revenue_trend: list[float] = []
