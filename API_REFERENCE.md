# MonoBooking API Reference

Base URL: `http://localhost:8000`
Auth: Bearer JWT token (from `/v1.0/signin/confirm`)

---

## Authentication (existing)

### POST /v1.0/signin — Request magic link
```bash
curl -X POST http://localhost:8000/v1.0/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@hotel.com"}'
```
**Response 201:**
```json
{"token": "abc123...", "expires_at": "2026-02-22T15:00:00Z"}
```

### POST /v1.0/signin/confirm — Confirm & get JWT
```bash
curl -X POST http://localhost:8000/v1.0/signin/confirm \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@hotel.com", "token": "abc123..."}'
```
**Response 200:**
```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "user": {"id": "uuid", "email": "owner@hotel.com", "name": "owner", "team_member_status": "accepted"}
}
```

---

## Properties

### GET /v1.0/properties — List user's properties
```bash
curl http://localhost:8000/v1.0/properties \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "items": [
    {
      "id": "prop-uuid-1",
      "account_id": "acct-uuid-1",
      "name": "Sunset Beach Resort",
      "street": "123 Ocean Drive",
      "city": "Miami Beach",
      "state": "FL",
      "postal_code": "33139",
      "country": "United States",
      "lat": 25.7825,
      "lng": -80.134,
      "floor": "1-5",
      "section": null,
      "property_number": "A-101",
      "description": "Luxury beachfront resort",
      "image_url": null,
      "rating": 4.9,
      "ai_match_score": 98,
      "created_at": "2026-02-22T10:00:00Z",
      "updated_at": "2026-02-22T10:00:00Z"
    }
  ]
}
```

### POST /v1.0/properties — Create property
```bash
curl -X POST http://localhost:8000/v1.0/properties \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Beach Hotel",
    "address": {
      "street": "100 Shore Blvd",
      "city": "Cancun",
      "country": "Mexico",
      "lat": 21.1619,
      "lng": -86.8515
    },
    "description": "Beachfront hotel in Cancun"
  }'
```
**Response 201:** `PropertyResponse` (same shape as list item)

### GET /v1.0/properties/{property_id} — Get single property
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:** `PropertyResponse`

### PATCH /v1.0/properties/{property_id} — Update property
```bash
curl -X PATCH http://localhost:8000/v1.0/properties/prop-uuid-1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sunset Beach Resort & Spa",
    "address": {"city": "Miami Beach", "state": "FL"}
  }'
```
**Response 200:** `PropertyResponse`

### DELETE /v1.0/properties/{property_id} — Delete property
```bash
curl -X DELETE http://localhost:8000/v1.0/properties/prop-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{"message": "Property deleted", "id": "prop-uuid-1"}
```

---

## Rooms

Notes:
- `currency_code` is accepted on create/update; existing and omitted values default to `USD`.
- Room responses include `currency_code` and `currency_display` for UI rendering.

### GET /v1.0/properties/{property_id}/rooms — List rooms
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/rooms \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "items": [
    {
      "id": "room-uuid-1",
      "property_id": "prop-uuid-1",
      "name": "Ocean View Deluxe Suite",
      "type": "Deluxe Suite",
      "description": "Spacious suite with panoramic ocean views...",
      "images": [],
      "price_per_night": 289.0,
      "currency_code": "USD",
      "currency_display": "$",
      "max_guests": 3,
      "bed_config": "1 King Bed",
      "amenities": ["WiFi", "Ocean View", "Balcony", "AC"],
      "source": "airbnb",
      "source_url": "https://airbnb.com/rooms/48291034",
      "sync_enabled": true,
      "last_synced": "2026-02-22T14:30:00Z",
      "status": "active",
      "created_at": "2026-02-22T10:00:00Z",
      "updated_at": "2026-02-22T10:00:00Z",
      "guest_tiers": [
        {"id": "tier-uuid", "min_guests": 1, "max_guests": 2, "price_per_night": 289.0},
        {"id": "tier-uuid", "min_guests": 3, "max_guests": 3, "price_per_night": 339.0}
      ],
      "date_overrides": [
        {"id": "dp-uuid", "date": "2026-02-28", "price": 350.0},
        {"id": "dp-uuid", "date": "2026-03-01", "price": 350.0}
      ]
    }
  ]
}
```

### POST /v1.0/properties/{property_id}/rooms — Create room
```bash
curl -X POST http://localhost:8000/v1.0/properties/prop-uuid-1/rooms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Beachfront Villa",
    "type": "Villa",
    "description": "Private villa with infinity pool",
    "price_per_night": 420,
    "currency_code": "UAH",
    "max_guests": 6,
    "bed_config": "1 King Bed + 2 Queen Beds",
    "amenities": ["WiFi", "Pool", "Beach Access", "Kitchen"],
    "source": "airbnb",
    "source_url": "https://airbnb.com/rooms/12345",
    "sync_enabled": true,
    "status": "active"
  }'
```
**Response 201:** `RoomResponse`

### GET /v1.0/properties/{property_id}/rooms/{room_id} — Get room
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/rooms/room-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:** `RoomResponse`

### PATCH /v1.0/properties/{property_id}/rooms/{room_id} — Update room
```bash
curl -X PATCH http://localhost:8000/v1.0/properties/prop-uuid-1/rooms/room-uuid-1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"price_per_night": 310, "sync_enabled": false}'
```
**Response 200:** `RoomResponse`

### DELETE /v1.0/properties/{property_id}/rooms/{room_id} — Delete room
```bash
curl -X DELETE http://localhost:8000/v1.0/properties/prop-uuid-1/rooms/room-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{"message": "Room deleted", "id": "room-uuid-1"}
```

### PUT /v1.0/properties/{property_id}/rooms/{room_id}/pricing — Set room pricing
```bash
curl -X PUT http://localhost:8000/v1.0/properties/prop-uuid-1/rooms/room-uuid-1/pricing \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date_overrides": [
      {"date": "2026-03-14", "price": 399},
      {"date": "2026-03-15", "price": 399}
    ],
    "guest_tiers": [
      {"min_guests": 1, "max_guests": 2, "price_per_night": 289},
      {"min_guests": 3, "max_guests": 3, "price_per_night": 339}
    ]
  }'
```
**Response 200:** `RoomResponse` (with updated pricing)

---

## Bookings

Notes:
- `currency_code` is optional on create; when omitted it is inherited from the room (fallback `USD`).
- Booking responses include `currency_code` and `currency_display`.

### GET /v1.0/properties/{property_id}/bookings — List bookings
```bash
# All bookings
curl http://localhost:8000/v1.0/properties/prop-uuid-1/bookings \
  -H "Authorization: Bearer $TOKEN"

# Filter by status
curl "http://localhost:8000/v1.0/properties/prop-uuid-1/bookings?status=confirmed" \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "items": [
    {
      "id": "booking-uuid-1",
      "property_id": "prop-uuid-1",
      "room_id": "room-uuid-1",
      "guest_id": "guest-uuid-1",
      "guest_name": "Sarah Chen",
      "check_in": "2026-03-15",
      "check_out": "2026-03-20",
      "total_price": 2100.0,
      "currency_code": "USD",
      "currency_display": "$",
      "status": "confirmed",
      "ai_handled": true,
      "source": "mcp",
      "conversation_id": "conv_abc123",
      "created_at": "2026-02-22T10:00:00Z",
      "updated_at": "2026-02-22T10:00:00Z",
      "cancelled_at": null
    }
  ]
}
```

### POST /v1.0/properties/{property_id}/bookings — Create booking
```bash
curl -X POST http://localhost:8000/v1.0/properties/prop-uuid-1/bookings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": "room-uuid-1",
    "guest_name": "John Doe",
    "guest_email": "john@example.com",
    "check_in": "2026-04-10",
    "check_out": "2026-04-15",
    "total_price": 1445,
    "currency_code": "USD",
    "status": "confirmed",
    "ai_handled": true,
    "source": "mcp",
    "conversation_id": "conv_xyz789"
  }'
```
**Response 201:** `BookingResponse`

### GET /v1.0/properties/{property_id}/bookings/{booking_id} — Get booking
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/bookings/booking-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:** `BookingResponse`

### PATCH /v1.0/properties/{property_id}/bookings/{booking_id} — Update booking
```bash
curl -X PATCH http://localhost:8000/v1.0/properties/prop-uuid-1/bookings/booking-uuid-1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "cancelled", "check_out": "2026-04-05"}'
```
**Response 200:** `BookingResponse`

---

## Audit Log

### GET /v1.0/properties/{property_id}/audit — List audit entries
```bash
# All entries
curl http://localhost:8000/v1.0/properties/prop-uuid-1/audit \
  -H "Authorization: Bearer $TOKEN"

# Filter by source, paginated
curl "http://localhost:8000/v1.0/properties/prop-uuid-1/audit?source=mcp&limit=10" \
  -H "Authorization: Bearer $TOKEN"

# Filter by inclusive created_at range (ISO datetimes)
curl "http://localhost:8000/v1.0/properties/prop-uuid-1/audit?from=2026-02-22T00:00:00Z&to=2026-02-22T23:59:59Z" \
  -H "Authorization: Bearer $TOKEN"
```
Query params:
- `source` (optional): one of `mcp`, `chatgpt`, `claude`, `gemini`, `widget`
- `from` (optional): ISO-8601 datetime, includes entries where `created_at >= from`
- `to` (optional): ISO-8601 datetime, includes entries where `created_at <= to`
- `limit` (optional): 1-100
- `cursor` (optional): pagination cursor from previous response

Notes:
- Date boundaries are inclusive.
- If both `from` and `to` are provided, `from` must be less than or equal to `to`.

**Response 200:**
```json
{
  "items": [
    {
      "id": "audit-uuid-1",
      "property_id": "prop-uuid-1",
      "conversation_id": "conv_abc123",
      "source": "mcp",
      "tool_name": "search_rooms",
      "description": "Searched available rooms for March 15-20",
      "status": "success",
      "request_payload": null,
      "response_payload": null,
      "created_at": "2026-02-22T14:32:00Z"
    }
  ],
  "next_cursor": null
}
```

---

## Host Profile

### GET /v1.0/properties/{property_id}/host-profile — Get host profile
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/host-profile \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "id": "hp-uuid",
  "property_id": "prop-uuid-1",
  "name": "StayAI Host",
  "location": "Miami, Florida",
  "bio": "We are passionate hosts who love creating memorable stays...",
  "avatar_url": null,
  "avatar_initials": "SH",
  "reviews": 142,
  "rating": 4.92,
  "years_hosting": 5,
  "superhost": true,
  "created_at": "2026-02-22T10:00:00Z",
  "updated_at": "2026-02-22T10:00:00Z"
}
```

### PUT /v1.0/properties/{property_id}/host-profile — Update host profile
```bash
curl -X PUT http://localhost:8000/v1.0/properties/prop-uuid-1/host-profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "StayAI Host",
    "location": "Miami, Florida",
    "bio": "Updated bio text",
    "reviews": 150,
    "rating": 4.95,
    "superhost": true
  }'
```
**Response 200:** `HostProfileResponse`

---

## Knowledge Files

### GET /v1.0/properties/{property_id}/knowledge-files — List files
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/knowledge-files \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "items": [
    {
      "id": "file-uuid-1",
      "property_id": "prop-uuid-1",
      "name": "Hotel_Policy_2026.pdf",
      "size": "2.4 MB",
      "storage_path": null,
      "mime_type": "application/pdf",
      "created_at": "2026-02-10T00:00:00Z"
    }
  ]
}
```

### POST /v1.0/properties/{property_id}/knowledge-files — Register file
```bash
curl -X POST http://localhost:8000/v1.0/properties/prop-uuid-1/knowledge-files \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Check_in_Guide.pdf", "size": "1.2 MB", "mime_type": "application/pdf"}'
```
**Response 201:** `KnowledgeFileResponse`

### DELETE /v1.0/properties/{property_id}/knowledge-files/{file_id} — Delete file
```bash
curl -X DELETE http://localhost:8000/v1.0/properties/prop-uuid-1/knowledge-files/file-uuid-1 \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{"message": "File deleted", "id": "file-uuid-1"}
```

---

## Settings: PMS Connections

### GET /v1.0/properties/{property_id}/pms-connections — List PMS connections
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/pms-connections \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "items": [
    {"id": "uuid", "property_id": "prop-uuid-1", "provider": "mews", "enabled": false, "config": {}, "created_at": "...", "updated_at": "..."},
    {"id": "uuid", "property_id": "prop-uuid-1", "provider": "cloudbeds", "enabled": false, "config": {}, "created_at": "...", "updated_at": "..."},
    {"id": "uuid", "property_id": "prop-uuid-1", "provider": "servio", "enabled": false, "config": {}, "created_at": "...", "updated_at": "..."}
  ]
}
```

### PUT /v1.0/properties/{property_id}/pms-connections/{provider} — Toggle PMS
```bash
curl -X PUT http://localhost:8000/v1.0/properties/prop-uuid-1/pms-connections/mews \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```
**Response 200:** `ConnectionResponse`

---

## Settings: Payment Connections

### GET /v1.0/properties/{property_id}/payment-connections — List payment providers
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/payment-connections \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:** Same shape as PMS connections list

### PUT /v1.0/properties/{property_id}/payment-connections/{provider} — Toggle payment
```bash
curl -X PUT http://localhost:8000/v1.0/properties/prop-uuid-1/payment-connections/stripe \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```
**Response 200:** `ConnectionResponse`

---

## Dashboard Metrics

### GET /v1.0/properties/{property_id}/metrics — Get dashboard KPIs
```bash
curl http://localhost:8000/v1.0/properties/prop-uuid-1/metrics \
  -H "Authorization: Bearer $TOKEN"
```
**Response 200:**
```json
{
  "ai_direct_bookings": 47,
  "commission_saved": 4650.0,
  "occupancy_rate": 87.0,
  "revenue": 22120.0,
  "ai_direct_bookings_trend": [12, 18, 15, 22, 28, 25, 32, 35, 30, 38, 42, 47],
  "commission_saved_trend": [1200, 1800, 2100, 2400, 2200, 2800, 3100, 2900, 3400, 3800, 4200, 4650],
  "occupancy_trend": [72, 78, 80, 82, 79, 85, 88, 84, 86, 89, 87, 87],
  "revenue_trend": [12000, 14500, 15200, 16800, 15500, 17200, 18400, 17800, 19200, 20500, 21100, 22120]
}
```

---

## Seed Data

### POST /v1.0/seed — Seed all mock data for current user
```bash
curl -X POST http://localhost:8000/v1.0/seed \
  -H "Authorization: Bearer $TOKEN"
```
**Response 201:**
```json
{
  "message": "Seed data created successfully",
  "properties": 3,
  "rooms": 4,
  "bookings": 8,
  "guests": 8,
  "audit_entries": 12,
  "knowledge_files": 3,
  "metrics_rows": 12,
  "property_ids": ["uuid-1", "uuid-2", "uuid-3"]
}
```
Idempotent: re-running deletes previous seed data for the user first.

---

## ChatGPT Apps / MCP

Remote MCP endpoint (Streamable HTTP):

- `POST /mcp`

Required header:

- `X-Monobook-MCP-Key: <MCP_SHARED_SECRET>`

Exposed tools:

- `search_hotels(query?, property_name?, city?, country?, room_name?, lat?, lng?, radius_km=20, check_in?, check_out?, guests?, pet_friendly?, budget_per_night_max?, budget_total_max?)`
- `search_rooms(property_id, query, check_in?, check_out?, guests?)`
- `check_availability(property_id, room_id, check_in, check_out)`
- `create_booking(property_id, room_id, guest_name, guest_email?, check_in, check_out, guests?)`

Notes:

- `search_hotels` applies all provided filters with AND logic and returns hotel-level results with nested `matching_rooms`.
- For `search_hotels`, at least one of `query`, `property_name`, `city`, `country`, `room_name`, or `lat/lng` is required.
- `search_hotels` requires `lat` and `lng` together.
- `search_hotels` validates `guests` with the same limits as booking tools.
- `search_hotels` applies availability filtering only when both `check_in` and `check_out` are provided.
- `search_hotels` treats `pet_friendly=true` as an amenities keyword filter (`pet friendly`, `pets allowed`, `pets welcome`, `pet-friendly`).
- `search_hotels` applies `budget_total_max` only when `check_in` + `check_out` are provided.
- Price-bearing tool responses include `currency_code` and `currency_display`.
- `property_id` must be a valid UUID.
- MCP-originated audit entries are stored with `source = "chatgpt"`.
- MCP booking creation writes bookings with `status = "confirmed"` and `source = "chatgpt"`.

---

## Error Responses

All errors follow this shape:
```json
{"detail": "Error message here"}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / validation error |
| 401 | Missing or invalid JWT token |
| 403 | No access to this property |
| 404 | Resource not found |
| 422 | Pydantic validation failure |
| 500 | Internal server error |
