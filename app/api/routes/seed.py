"""Seed endpoint: inserts all mock data for the current authenticated user.

POST /v1.0/seed
- Creates 3 properties (accounts + property records) for the current user
- Creates host profiles for each property
- Creates rooms with pricing (date overrides + guest tiers)
- Creates services catalog (categories, partners, services, slots, bookings)
- Creates guests, chat sessions/messages, and bookings
- Creates audit log entries
- Creates knowledge base files
- Creates dashboard metrics (12 months)
- Creates PMS and payment connection records
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.service import create_service, create_service_category, create_service_partner
from app.db.base import get_supabase

router = APIRouter(prefix="/v1.0", tags=["seed"])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_data(
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Seed all mock data for the current user. Idempotent — deletes previous seed data first."""
    user_id = current_user["id"]

    # Clean previous seed data for this user (cascade handles children)
    existing = (
        client.table("accounts")
        .select("id")
        .eq("created_by", user_id)
        .eq("is_default", False)
        .execute()
    )
    for acct in existing.data or []:
        client.table("accounts").delete().eq("id", acct["id"]).execute()

    # ── 1. Properties (3 accounts + 3 property rows) ─────────────────────
    properties_data = [
        {
            "account_name": "Sunset Beach Resort",
            "street": "123 Ocean Drive",
            "city": "Miami Beach",
            "state": "FL",
            "postal_code": "33139",
            "country": "United States",
            "lat": 25.7825,
            "lng": -80.1340,
            "floor": "1-5",
            "property_number": "A-101",
            "description": "Luxury beachfront resort with panoramic ocean views",
            "rating": 4.9,
            "ai_match_score": 98,
        },
        {
            "account_name": "Downtown City Hotel",
            "street": "456 Main Street",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "United States",
            "lat": 40.7484,
            "lng": -73.9967,
            "section": "West Wing",
            "description": "Modern city hotel in the heart of Manhattan",
            "rating": 4.8,
            "ai_match_score": 94,
        },
        {
            "account_name": "Mountain Lodge Retreat",
            "street": "789 Alpine Road",
            "city": "Aspen",
            "state": "CO",
            "postal_code": "81611",
            "country": "United States",
            "lat": 39.1911,
            "lng": -106.8175,
            "floor": "Ground",
            "section": "Main Lodge",
            "property_number": "ML-01",
            "description": "Charming alpine lodge with mountain views and ski access",
            "rating": 4.7,
            "ai_match_score": 87,
        },
    ]

    property_ids = []
    for pd in properties_data:
        name = pd.pop("account_name")
        acct = (
            client.table("accounts")
            .insert({"name": name, "is_default": False, "created_by": user_id})
            .execute()
        )
        account_id = acct.data[0]["id"]

        client.table("team_members").insert(
            {"account_id": account_id, "user_id": user_id, "role": "admin", "status": "accepted"}
        ).execute()

        prop = (
            client.table("properties")
            .insert({"account_id": account_id, **pd})
            .execute()
        )
        property_ids.append(prop.data[0]["id"])

    pid1, pid2, pid3 = property_ids

    # ── 2. Host profiles ─────────────────────────────────────────────────
    host_profiles = [
        {
            "property_id": pid1,
            "name": "StayAI Host",
            "location": "Miami, Florida",
            "bio": "We are passionate hosts who love creating memorable stays for our guests. With years of experience in hospitality, we ensure every detail is perfect.",
            "avatar_initials": "SH",
            "reviews": 142,
            "rating": 4.92,
            "years_hosting": 5,
            "superhost": True,
        },
        {
            "property_id": pid2,
            "name": "City Stays NYC",
            "location": "New York, NY",
            "bio": "Premium city accommodation in the heart of Manhattan.",
            "avatar_initials": "CS",
            "reviews": 89,
            "rating": 4.85,
            "years_hosting": 3,
            "superhost": False,
        },
        {
            "property_id": pid3,
            "name": "Alpine Escapes",
            "location": "Aspen, Colorado",
            "bio": "Mountain retreat specialists with a passion for outdoor adventure.",
            "avatar_initials": "AE",
            "reviews": 210,
            "rating": 4.95,
            "years_hosting": 8,
            "superhost": True,
        },
    ]
    client.table("host_profiles").insert(host_profiles).execute()

    # ── 3. Rooms ─────────────────────────────────────────────────────────
    rooms_data = [
        {
            "property_id": pid1,
            "name": "Ocean View Deluxe Suite",
            "type": "Deluxe Suite",
            "description": "Spacious suite with panoramic ocean views, private balcony, and luxurious furnishings. Features a king-size bed, marble bathroom with rain shower, and a separate living area perfect for relaxation.",
            "images": [],
            "price_per_night": 289,
            "max_guests": 3,
            "bed_config": "1 King Bed",
            "amenities": ["WiFi", "Ocean View", "Balcony", "AC", "Mini Bar", "Room Service", "Safe", "Flat-screen TV"],
            "source": "airbnb",
            "source_url": "https://airbnb.com/rooms/48291034",
            "sync_enabled": True,
            "last_synced": "2026-02-22T14:30:00Z",
            "status": "active",
        },
        {
            "property_id": pid1,
            "name": "Garden Family Room",
            "type": "Family Room",
            "description": "A warm, family-friendly room overlooking the tropical garden. Comes with two queen beds, a children's play corner, and direct pool access.",
            "images": [],
            "price_per_night": 195,
            "max_guests": 4,
            "bed_config": "2 Queen Beds",
            "amenities": ["WiFi", "Garden View", "Pool Access", "AC", "Kitchen", "Parking", "Crib Available"],
            "source": "booking",
            "source_url": "https://booking.com/hotel/us/example.html",
            "sync_enabled": True,
            "last_synced": "2026-02-21T09:15:00Z",
            "status": "active",
        },
        {
            "property_id": pid2,
            "name": "Standard Twin Room",
            "type": "Standard Room",
            "description": "Comfortable twin room ideal for friends or colleagues traveling together. Clean, modern design with all essential amenities.",
            "images": [],
            "price_per_night": 120,
            "max_guests": 2,
            "bed_config": "2 Twin Beds",
            "amenities": ["WiFi", "AC", "Flat-screen TV", "Desk", "Parking"],
            "source": "manual",
            "sync_enabled": False,
            "status": "active",
        },
        {
            "property_id": pid3,
            "name": "Presidential Penthouse",
            "type": "Penthouse",
            "description": "The crown jewel of our property. A stunning two-floor penthouse with 360-degree city views, private jacuzzi, chef's kitchen, and dedicated butler service.",
            "images": [],
            "price_per_night": 750,
            "max_guests": 6,
            "bed_config": "1 King Bed + 2 Single Beds",
            "amenities": ["WiFi", "City View", "Jacuzzi", "Kitchen", "Butler Service", "AC", "Mini Bar", "Gym Access", "Spa Access"],
            "source": "airbnb",
            "source_url": "https://airbnb.com/rooms/90128374",
            "sync_enabled": False,
            "last_synced": "2026-02-18T20:00:00Z",
            "status": "draft",
        },
    ]

    room_resp = client.table("rooms").insert(rooms_data).execute()
    room_ids = [r["id"] for r in room_resp.data]
    rid1, rid2, rid3, rid4 = room_ids

    # ── 4. Room pricing ──────────────────────────────────────────────────
    date_overrides = [
        {"room_id": rid1, "date": "2026-02-28", "price": 350},
        {"room_id": rid1, "date": "2026-03-01", "price": 350},
        {"room_id": rid1, "date": "2026-03-14", "price": 399},
        {"room_id": rid1, "date": "2026-03-15", "price": 399},
        {"room_id": rid4, "date": "2026-03-06", "price": 899},
        {"room_id": rid4, "date": "2026-03-07", "price": 899},
        {"room_id": rid4, "date": "2026-03-08", "price": 899},
    ]
    client.table("room_date_pricing").insert(date_overrides).execute()

    guest_tiers = [
        {"room_id": rid1, "min_guests": 1, "max_guests": 2, "price_per_night": 289},
        {"room_id": rid1, "min_guests": 3, "max_guests": 3, "price_per_night": 339},
        {"room_id": rid4, "min_guests": 1, "max_guests": 2, "price_per_night": 750},
        {"room_id": rid4, "min_guests": 3, "max_guests": 4, "price_per_night": 850},
        {"room_id": rid4, "min_guests": 5, "max_guests": 6, "price_per_night": 950},
    ]
    client.table("room_guest_tiers").insert(guest_tiers).execute()

    # ── 5. Guests ────────────────────────────────────────────────────────
    guests_data = [
        {
            "property_id": pid1,
            "name": "Sarah Chen",
            "email": "sarah.chen@example.com",
            "phone": "+1 415-555-0142",
            "notes": "Prefers high floor and feather-free pillows",
        },
        {
            "property_id": pid1,
            "name": "James Wilson",
            "email": "james.wilson@example.com",
            "phone": "+1 646-555-0148",
            "notes": "",
        },
        {
            "property_id": pid1,
            "name": "Maria Garcia",
            "email": "maria.garcia@example.com",
            "phone": "+34 91 555 0132",
            "notes": "Early check-in preferred when available",
        },
        {
            "property_id": pid1,
            "name": "Alex Thompson",
            "email": "alex.thompson@example.com",
            "phone": "+1 303-555-0110",
            "notes": "",
        },
        {
            "property_id": pid1,
            "name": "Yuki Tanaka",
            "email": "yuki.tanaka@example.com",
            "phone": "+81 3-5555-0191",
            "notes": "Vegetarian breakfast",
        },
        {
            "property_id": pid1,
            "name": "Alex Kim",
            "email": "alex.kim@example.com",
            "phone": "+1 917-555-0193",
            "notes": "",
        },
        {
            "property_id": pid1,
            "name": "Emma Laurent",
            "email": "emma.laurent@example.com",
            "phone": "+33 1 55 55 01 74",
            "notes": "",
        },
        {
            "property_id": pid1,
            "name": "David Park",
            "email": "david.park@example.com",
            "phone": "+1 213-555-0175",
            "notes": "",
        },
    ]
    guests_resp = client.table("guests").insert(guests_data).execute()
    guest_map = {g["name"]: g["id"] for g in guests_resp.data}

    # ── 6. Guest chat sessions + messages ───────────────────────────────
    sessions_data = [
        {
            "property_id": pid1,
            "guest_id": guest_map["Sarah Chen"],
            "guest_name": "Sarah Chen",
            "guest_email": "sarah.chen@example.com",
            "source": "widget",
            "created_at": "2026-02-17T09:30:00Z",
            "updated_at": "2026-02-17T09:31:20Z",
        },
        {
            "property_id": pid1,
            "guest_id": guest_map["James Wilson"],
            "guest_name": "James Wilson",
            "guest_email": "james.wilson@example.com",
            "source": "chatgpt",
            "created_at": "2026-02-15T11:00:00Z",
            "updated_at": "2026-02-15T11:01:00Z",
        },
        {
            "property_id": pid1,
            "guest_id": guest_map["Maria Garcia"],
            "guest_name": "Maria Garcia",
            "guest_email": "maria.garcia@example.com",
            "source": "claude",
            "created_at": "2026-02-19T16:00:00Z",
            "updated_at": "2026-02-19T16:01:25Z",
        },
        {
            "property_id": pid1,
            "guest_id": guest_map["Yuki Tanaka"],
            "guest_name": "Yuki Tanaka",
            "guest_email": "yuki.tanaka@example.com",
            "source": "widget",
            "created_at": "2026-02-21T08:00:00Z",
            "updated_at": "2026-02-21T08:01:10Z",
        },
    ]
    sessions_resp = client.table("chat_sessions").insert(sessions_data).execute()
    session_map = {session["guest_name"]: session["id"] for session in sessions_resp.data}

    messages_data = [
        {
            "session_id": session_map["Sarah Chen"],
            "role": "user",
            "content": "Hi, I'd like to book the Ocean View Suite for Feb 18-20",
            "created_at": "2026-02-17T09:30:00Z",
        },
        {
            "session_id": session_map["Sarah Chen"],
            "role": "assistant",
            "content": "The Ocean View Deluxe Suite is available for those dates at $289/night. Shall I proceed?",
            "created_at": "2026-02-17T09:30:15Z",
        },
        {
            "session_id": session_map["Sarah Chen"],
            "role": "user",
            "content": "Yes please, and could I get a high floor?",
            "created_at": "2026-02-17T09:31:00Z",
        },
        {
            "session_id": session_map["Sarah Chen"],
            "role": "assistant",
            "content": "Absolutely. I've added your high-floor request and confirmed your booking.",
            "created_at": "2026-02-17T09:31:20Z",
        },
        {
            "session_id": session_map["James Wilson"],
            "role": "user",
            "content": "Do you have anything available for tomorrow night?",
            "created_at": "2026-02-15T11:00:00Z",
        },
        {
            "session_id": session_map["James Wilson"],
            "role": "assistant",
            "content": "Yes, a Standard Room is available at $170/night for Feb 16-18.",
            "created_at": "2026-02-15T11:00:12Z",
        },
        {
            "session_id": session_map["Maria Garcia"],
            "role": "user",
            "content": "I need the Penthouse for Feb 20-22.",
            "created_at": "2026-02-19T16:00:00Z",
        },
        {
            "session_id": session_map["Maria Garcia"],
            "role": "assistant",
            "content": "Penthouse Suite is available for those dates at $490/night.",
            "created_at": "2026-02-19T16:00:18Z",
        },
        {
            "session_id": session_map["Yuki Tanaka"],
            "role": "user",
            "content": "Bonjour! I'd like to confirm my upcoming stay.",
            "created_at": "2026-02-21T08:00:00Z",
        },
        {
            "session_id": session_map["Yuki Tanaka"],
            "role": "assistant",
            "content": "Everything is confirmed. We look forward to hosting you.",
            "created_at": "2026-02-21T08:01:10Z",
        },
    ]
    client.table("chat_messages").insert(messages_data).execute()

    # ── 7. Bookings ──────────────────────────────────────────────────────
    bookings_data = [
        {
            "property_id": pid1, "room_id": rid1, "guest_id": guest_map["Sarah Chen"],
            "check_in": "2026-03-15", "check_out": "2026-03-20", "total_price": 2100,
            "status": "confirmed", "ai_handled": True, "source": "mcp",
            "conversation_id": session_map["Sarah Chen"],
        },
        {
            "property_id": pid1, "room_id": rid2, "guest_id": guest_map["James Wilson"],
            "check_in": "2026-03-22", "check_out": "2026-03-25", "total_price": 1260,
            "status": "confirmed", "ai_handled": True, "source": "chatgpt",
            "conversation_id": session_map["James Wilson"],
        },
        {
            "property_id": pid1, "room_id": rid1, "guest_id": guest_map["Maria Garcia"],
            "check_in": "2026-03-18", "check_out": "2026-03-21", "total_price": 1260,
            "status": "ai_pending", "ai_handled": True, "source": "claude",
            "conversation_id": session_map["Maria Garcia"],
        },
        {
            "property_id": pid1, "room_id": rid2, "guest_id": guest_map["Alex Thompson"],
            "check_in": "2026-04-01", "check_out": "2026-04-05", "total_price": 1680,
            "status": "pending", "ai_handled": False,
        },
        {
            "property_id": pid1, "room_id": rid1, "guest_id": guest_map["Yuki Tanaka"],
            "check_in": "2026-03-28", "check_out": "2026-04-02", "total_price": 2520,
            "status": "confirmed", "ai_handled": True, "source": "widget",
            "conversation_id": session_map["Yuki Tanaka"],
        },
        {
            "property_id": pid1, "room_id": rid1, "guest_id": guest_map["Alex Kim"],
            "check_in": "2026-03-25", "check_out": "2026-03-28", "total_price": 867,
            "status": "ai_pending", "ai_handled": True, "source": "mcp",
        },
        {
            "property_id": pid1, "room_id": rid2, "guest_id": guest_map["Emma Laurent"],
            "check_in": "2026-03-14", "check_out": "2026-03-18", "total_price": 780,
            "status": "confirmed", "ai_handled": False, "source": "widget",
        },
        {
            "property_id": pid1, "room_id": rid2, "guest_id": guest_map["David Park"],
            "check_in": "2026-03-20", "check_out": "2026-03-24", "total_price": 780,
            "status": "confirmed", "ai_handled": True, "source": "gemini",
        },
    ]
    client.table("bookings").insert(bookings_data).execute()

    # ── 8. Audit log ─────────────────────────────────────────────────────
    audit_data = [
        {"property_id": pid1, "conversation_id": "conv_abc123", "source": "mcp", "tool_name": "search_rooms", "description": "Searched available rooms for March 15-20", "status": "success", "created_at": "2026-02-22T14:32:00Z"},
        {"property_id": pid1, "conversation_id": "conv_abc123", "source": "mcp", "tool_name": "create_booking", "description": "Created booking for Sarah Chen, Room 301", "status": "success", "created_at": "2026-02-22T14:33:12Z"},
        {"property_id": pid1, "conversation_id": "conv_def456", "source": "chatgpt", "tool_name": "check_availability", "description": "Checked availability for Deluxe Suite", "status": "success", "created_at": "2026-02-22T12:15:00Z"},
        {"property_id": pid1, "conversation_id": "conv_ghi789", "source": "claude", "tool_name": "get_pricing", "description": "Retrieved pricing for Penthouse Suite", "status": "success", "created_at": "2026-02-22T11:45:30Z"},
        {"property_id": pid1, "conversation_id": "conv_jkl012", "source": "gemini", "tool_name": "search_rooms", "description": "Searched rooms with sea view amenity", "status": "error", "created_at": "2026-02-22T10:20:00Z"},
        {"property_id": pid1, "conversation_id": "conv_mno345", "source": "widget", "tool_name": "create_booking", "description": "Guest initiated booking via widget", "status": "success", "created_at": "2026-02-21T18:05:00Z"},
        {"property_id": pid1, "conversation_id": "conv_pqr678", "source": "chatgpt", "tool_name": "cancel_booking", "description": "Cancelled booking b4 for Alex Thompson", "status": "pending", "created_at": "2026-02-21T16:40:00Z"},
        {"property_id": pid1, "conversation_id": "conv_stu901", "source": "claude", "tool_name": "update_booking", "description": "Extended checkout date to April 5", "status": "success", "created_at": "2026-02-21T15:12:00Z"},
        {"property_id": pid1, "conversation_id": "conv_vwx234", "source": "mcp", "tool_name": "get_guest_info", "description": "Retrieved guest profile for Yuki Tanaka", "status": "success", "created_at": "2026-02-21T14:00:00Z"},
        {"property_id": pid1, "conversation_id": "conv_yza567", "source": "gemini", "tool_name": "search_rooms", "description": "Searched available rooms for April", "status": "success", "created_at": "2026-02-21T11:30:00Z"},
        {"property_id": pid1, "conversation_id": "conv_bcd890", "source": "widget", "tool_name": "check_availability", "description": "Widget availability check for Mountain Suite", "status": "success", "created_at": "2026-02-20T20:15:00Z"},
        {"property_id": pid1, "conversation_id": "conv_efg123", "source": "chatgpt", "tool_name": "create_booking", "description": "Failed to create booking — room unavailable", "status": "error", "created_at": "2026-02-20T17:45:00Z"},
    ]
    client.table("audit_log").insert(audit_data).execute()

    # ── 9. Knowledge base files ──────────────────────────────────────────
    files_data = [
        {"property_id": pid1, "name": "Hotel_Policy_2026.pdf", "size": "2.4 MB", "mime_type": "application/pdf", "created_at": "2026-02-10T00:00:00Z"},
        {"property_id": pid1, "name": "WiFi_Instructions.docx", "size": "145 KB", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "created_at": "2026-02-12T00:00:00Z"},
        {"property_id": pid1, "name": "Restaurant_Menu.pdf", "size": "5.1 MB", "mime_type": "application/pdf", "created_at": "2026-02-15T00:00:00Z"},
    ]
    client.table("knowledge_files").insert(files_data).execute()

    # ── 10. Dashboard metrics (12 months for property 1) ─────────────────
    ai_bookings = [12, 18, 15, 22, 28, 25, 32, 35, 30, 38, 42, 47]
    commissions = [1200, 1800, 2100, 2400, 2200, 2800, 3100, 2900, 3400, 3800, 4200, 4650]
    occupancy = [72, 78, 80, 82, 79, 85, 88, 84, 86, 89, 87, 87]
    revenues = [12000, 14500, 15200, 16800, 15500, 17200, 18400, 17800, 19200, 20500, 21100, 22120]

    today = date.today()
    metrics_rows = []
    for i in range(12):
        d = today - timedelta(days=(11 - i) * 30)
        metrics_rows.append({
            "property_id": pid1,
            "date": d.isoformat(),
            "ai_direct_bookings": ai_bookings[i],
            "commission_saved": commissions[i],
            "occupancy_rate": occupancy[i],
            "revenue": revenues[i],
        })
    client.table("dashboard_metrics").insert(metrics_rows).execute()

    # ── 11. PMS connections ──────────────────────────────────────────────
    pms_rows = [
        {"property_id": pid1, "provider": "mews", "enabled": False},
        {"property_id": pid1, "provider": "cloudbeds", "enabled": False},
        {"property_id": pid1, "provider": "servio", "enabled": False},
    ]
    client.table("pms_connections").insert(pms_rows).execute()

    # ── 12. Payment connections ──────────────────────────────────────────
    pay_rows = [
        {"property_id": pid1, "provider": "stripe", "enabled": False},
        {"property_id": pid1, "provider": "jpmorgan", "enabled": False},
        {"property_id": pid1, "provider": "ipay", "enabled": False},
        {"property_id": pid1, "provider": "liqpay", "enabled": False},
        {"property_id": pid1, "provider": "monobank", "enabled": False},
    ]
    client.table("payment_connections").insert(pay_rows).execute()

    # ── 13. Services (categories, partners, services, slots, bookings, analytics) ──
    category_seed = [
        {
            "slug": "spa-wellness",
            "name": "Spa & Wellness",
            "description": "Relaxation and body treatments",
            "icon": "🧖",
        },
        {
            "slug": "dining-drinks",
            "name": "Dining & Drinks",
            "description": "Restaurant and bar offerings",
            "icon": "🍽️",
        },
        {
            "slug": "activities",
            "name": "Activities",
            "description": "Tours, excursions, and entertainment",
            "icon": "🎯",
        },
        {
            "slug": "transport",
            "name": "Transport",
            "description": "Airport transfers and car rental",
            "icon": "🚗",
        },
        {
            "slug": "essentials",
            "name": "Essentials",
            "description": "Toiletries, chargers, and extras",
            "icon": "🧴",
        },
    ]

    partner_seed = [
        {
            "slug": "city-tours-ltd",
            "name": "City Tours Ltd.",
            "revenue_share_percent": 15.0,
            "payout_type": "manual",
            "status": "active",
        },
        {
            "slug": "relax-spa-group",
            "name": "Relax Spa Group",
            "revenue_share_percent": 20.0,
            "payout_type": "manual",
            "status": "active",
        },
        {
            "slug": "green-transfers",
            "name": "Green Transfers",
            "revenue_share_percent": 10.0,
            "payout_type": "manual",
            "status": "inactive",
        },
    ]

    service_seed = [
        {
            "slug": "deep-tissue-massage",
            "name": "Deep Tissue Massage",
            "short_description": "60-minute deep tissue massage in-room or spa",
            "full_description": "A therapeutic full-body massage targeting muscle tension and stress relief. Available in-room or at the hotel spa.",
            "image_urls": [
                "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=1200&h=800&fit=crop"
            ],
            "type": "internal",
            "category_slug": "spa-wellness",
            "partner_slug": None,
            "status": "active",
            "visibility": "public",
            "pricing_type": "fixed",
            "price": 89.00,
            "currency_code": "USD",
            "vat_percent": 20.00,
            "allow_discount": True,
            "bundle_eligible": True,
            "availability_type": "time_slot",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": False,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": 10.00,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 24.00,
            "total_bookings": 187,
            "revenue_30d": 5340.00,
            "conversion_rate": 18.00,
            "slots": [
                {"time": "09:00", "capacity": 2, "booked": 2, "sort_order": 1},
                {"time": "11:00", "capacity": 2, "booked": 1, "sort_order": 2},
                {"time": "14:00", "capacity": 2, "booked": 0, "sort_order": 3},
                {"time": "16:00", "capacity": 2, "booked": 0, "sort_order": 4},
            ],
        },
        {
            "slug": "airport-transfer",
            "name": "Airport Transfer",
            "short_description": "Private car transfer to/from airport",
            "full_description": "Comfortable private sedan or minivan transfer between the hotel and the nearest airport. Book up to 24h before arrival.",
            "image_urls": [
                "https://images.unsplash.com/photo-1549317661-bd32c8ce0afa?w=1200&h=800&fit=crop"
            ],
            "type": "partner",
            "category_slug": "transport",
            "partner_slug": "green-transfers",
            "status": "active",
            "visibility": "after_booking",
            "pricing_type": "fixed",
            "price": 45.00,
            "currency_code": "USD",
            "vat_percent": 10.00,
            "allow_discount": False,
            "bundle_eligible": True,
            "availability_type": "linked_booking",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": False,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": None,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 38.00,
            "total_bookings": 312,
            "revenue_30d": 8100.00,
            "conversion_rate": 32.00,
            "slots": [],
        },
        {
            "slug": "romantic-dinner-package",
            "name": "Romantic Dinner Package",
            "short_description": "4-course dinner with wine pairing for two",
            "full_description": "An exclusive candlelit 4-course dinner at the rooftop restaurant with curated wine pairing. Perfect for special occasions.",
            "image_urls": [
                "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1200&h=800&fit=crop"
            ],
            "type": "internal",
            "category_slug": "dining-drinks",
            "partner_slug": None,
            "status": "active",
            "visibility": "public",
            "pricing_type": "per_person",
            "price": 120.00,
            "currency_code": "USD",
            "vat_percent": 20.00,
            "allow_discount": True,
            "bundle_eligible": False,
            "availability_type": "date_range",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": False,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": None,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 12.00,
            "total_bookings": 64,
            "revenue_30d": 3840.00,
            "conversion_rate": 9.00,
            "slots": [],
        },
        {
            "slug": "city-walking-tour",
            "name": "City Walking Tour",
            "short_description": "Guided 3-hour tour of Old Town highlights",
            "full_description": "Explore the city's top landmarks with a certified local guide. Includes skip-the-line museum entry and a coffee stop.",
            "image_urls": [
                "https://images.unsplash.com/photo-1569949381669-ecf31ae8f613?w=1200&h=800&fit=crop"
            ],
            "type": "partner",
            "category_slug": "activities",
            "partner_slug": "city-tours-ltd",
            "status": "draft",
            "visibility": "public",
            "pricing_type": "per_person",
            "price": 35.00,
            "currency_code": "USD",
            "vat_percent": 10.00,
            "allow_discount": True,
            "bundle_eligible": True,
            "availability_type": "time_slot",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": False,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": None,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 8.00,
            "total_bookings": 42,
            "revenue_30d": 980.00,
            "conversion_rate": 6.00,
            "slots": [
                {"time": "10:00", "capacity": 12, "booked": 8, "sort_order": 1},
                {"time": "15:00", "capacity": 12, "booked": 3, "sort_order": 2},
            ],
        },
        {
            "slug": "premium-toiletry-kit",
            "name": "Premium Toiletry Kit",
            "short_description": "Luxury travel-size toiletry set",
            "full_description": "Eco-friendly premium toiletry kit including shampoo, conditioner, body wash, and moisturizer in reusable containers.",
            "image_urls": [
                "https://images.unsplash.com/photo-1556228578-8c89e6adf883?w=1200&h=800&fit=crop"
            ],
            "type": "product",
            "category_slug": "essentials",
            "partner_slug": None,
            "status": "active",
            "visibility": "during_stay",
            "pricing_type": "fixed",
            "price": 25.00,
            "currency_code": "USD",
            "vat_percent": 20.00,
            "allow_discount": False,
            "bundle_eligible": True,
            "availability_type": "always",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": True,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": None,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 15.00,
            "total_bookings": 203,
            "revenue_30d": 1525.00,
            "conversion_rate": 12.00,
            "slots": [],
        },
        {
            "slug": "yoga-session",
            "name": "Yoga Session",
            "short_description": "Morning rooftop yoga class",
            "full_description": "Start your day with a 45-minute guided yoga session on the rooftop terrace. Mats and water provided.",
            "image_urls": [
                "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&h=800&fit=crop"
            ],
            "type": "internal",
            "category_slug": "spa-wellness",
            "partner_slug": None,
            "status": "hidden",
            "visibility": "public",
            "pricing_type": "per_person",
            "price": 20.00,
            "currency_code": "USD",
            "vat_percent": 20.00,
            "allow_discount": True,
            "bundle_eligible": False,
            "availability_type": "time_slot",
            "capacity_mode": "unlimited",
            "capacity_limit": None,
            "recurring_schedule_enabled": False,
            "available_before_booking": True,
            "available_during_booking": True,
            "post_booking_upsell": False,
            "in_stay_qr_ordering": False,
            "upsell_trigger_room_type": "any",
            "early_booking_discount_percent": None,
            "knowledge_language": "en",
            "knowledge_ai_search_enabled": True,
            "attach_rate": 20.00,
            "total_bookings": 156,
            "revenue_30d": 2200.00,
            "conversion_rate": 15.00,
            "slots": [
                {"time": "07:00", "capacity": 10, "booked": 10, "sort_order": 1},
                {"time": "08:00", "capacity": 10, "booked": 5, "sort_order": 2},
            ],
        },
    ]

    service_booking_seed = [
        {
            "external_ref": "sb-1",
            "service_slug": "deep-tissue-massage",
            "guest_name": "Anna Muller",
            "service_date": "2026-02-28",
            "quantity": 1,
            "total": 89.00,
            "status": "confirmed",
        },
        {
            "external_ref": "sb-2",
            "service_slug": "deep-tissue-massage",
            "guest_name": "James Lee",
            "service_date": "2026-02-27",
            "quantity": 2,
            "total": 178.00,
            "status": "confirmed",
        },
        {
            "external_ref": "sb-3",
            "service_slug": "airport-transfer",
            "guest_name": "Sophie Martin",
            "service_date": "2026-02-26",
            "quantity": 1,
            "total": 45.00,
            "status": "pending",
        },
        {
            "external_ref": "sb-4",
            "service_slug": "romantic-dinner-package",
            "guest_name": "Carlos Rivera",
            "service_date": "2026-02-25",
            "quantity": 2,
            "total": 240.00,
            "status": "confirmed",
        },
        {
            "external_ref": "sb-5",
            "service_slug": "premium-toiletry-kit",
            "guest_name": "Emily Wang",
            "service_date": "2026-02-24",
            "quantity": 3,
            "total": 75.00,
            "status": "confirmed",
        },
        {
            "external_ref": "sb-6",
            "service_slug": "city-walking-tour",
            "guest_name": "Oliver Brown",
            "service_date": "2026-02-23",
            "quantity": 1,
            "total": 35.00,
            "status": "cancelled",
        },
        {
            "external_ref": "sb-7",
            "service_slug": "yoga-session",
            "guest_name": "Yuki Tanaka",
            "service_date": "2026-02-22",
            "quantity": 1,
            "total": 20.00,
            "status": "confirmed",
        },
    ]

    service_revenue_seed = [
        {"month": "2025-09-01", "revenue": 4200.00},
        {"month": "2025-10-01", "revenue": 5800.00},
        {"month": "2025-11-01", "revenue": 6100.00},
        {"month": "2025-12-01", "revenue": 8400.00},
        {"month": "2026-01-01", "revenue": 7200.00},
        {"month": "2026-02-01", "revenue": 9100.00},
    ]

    seeded_service_categories = 0
    seeded_service_partners = 0
    seeded_services = 0
    seeded_service_bookings = 0
    seeded_service_revenue_points = 0

    for property_id in property_ids:
        category_ids_by_slug: dict[str, str] = {}
        for idx, category in enumerate(category_seed):
            created_category = await create_service_category(
                client,
                property_id,
                {
                    "name": category["name"],
                    "description": category["description"],
                    "icon": category["icon"],
                    "sort_order": idx + 1,
                },
            )
            category_id = created_category.get("id")
            if category_id:
                category_ids_by_slug[category["slug"]] = category_id
                seeded_service_categories += 1

        partner_ids_by_slug: dict[str, str] = {}
        for partner in partner_seed:
            created_partner = await create_service_partner(
                client,
                property_id,
                {
                    "name": partner["name"],
                    "revenue_share_percent": partner["revenue_share_percent"],
                    "payout_type": partner["payout_type"],
                    "status": partner["status"],
                },
            )
            partner_id = created_partner.get("id")
            if partner_id:
                partner_ids_by_slug[partner["slug"]] = partner_id
                seeded_service_partners += 1

        service_ids_by_slug: dict[str, str] = {}
        for service in service_seed:
            payload = {
                "name": service["name"],
                "short_description": service["short_description"],
                "full_description": service["full_description"],
                "image_urls": service["image_urls"],
                "type": service["type"],
                "category_id": category_ids_by_slug.get(service["category_slug"]),
                "partner_id": partner_ids_by_slug.get(service["partner_slug"]),
                "status": service["status"],
                "visibility": service["visibility"],
                "pricing_type": service["pricing_type"],
                "price": service["price"],
                "currency_code": service["currency_code"],
                "vat_percent": service["vat_percent"],
                "allow_discount": service["allow_discount"],
                "bundle_eligible": service["bundle_eligible"],
                "availability_type": service["availability_type"],
                "capacity_mode": service["capacity_mode"],
                "capacity_limit": service["capacity_limit"],
                "recurring_schedule_enabled": service["recurring_schedule_enabled"],
                "available_before_booking": service["available_before_booking"],
                "available_during_booking": service["available_during_booking"],
                "post_booking_upsell": service["post_booking_upsell"],
                "in_stay_qr_ordering": service["in_stay_qr_ordering"],
                "upsell_trigger_room_type": service["upsell_trigger_room_type"],
                "early_booking_discount_percent": service["early_booking_discount_percent"],
                "knowledge_language": service["knowledge_language"],
                "knowledge_ai_search_enabled": service["knowledge_ai_search_enabled"],
                "attach_rate": service["attach_rate"],
                "total_bookings": service["total_bookings"],
                "revenue_30d": service["revenue_30d"],
                "conversion_rate": service["conversion_rate"],
                "slots": service["slots"],
            }
            created_service = await create_service(client, property_id, payload)
            service_id = created_service.get("id")
            if service_id:
                service_ids_by_slug[service["slug"]] = service_id
                seeded_services += 1

        booking_rows = []
        for booking in service_booking_seed:
            service_id = service_ids_by_slug.get(booking["service_slug"])
            if not service_id:
                continue
            booking_rows.append(
                {
                    "property_id": property_id,
                    "service_id": service_id,
                    "external_ref": booking["external_ref"],
                    "guest_name": booking["guest_name"],
                    "service_date": booking["service_date"],
                    "quantity": booking["quantity"],
                    "total": booking["total"],
                    "currency_code": "USD",
                    "status": booking["status"],
                }
            )
        if booking_rows:
            client.table("service_bookings").insert(booking_rows).execute()
            seeded_service_bookings += len(booking_rows)

        revenue_rows = [
            {
                "property_id": property_id,
                "month": point["month"],
                "revenue": point["revenue"],
            }
            for point in service_revenue_seed
        ]
        if revenue_rows:
            client.table("service_revenue_monthly").insert(revenue_rows).execute()
            seeded_service_revenue_points += len(revenue_rows)

    return {
        "message": "Seed data created successfully",
        "properties": len(property_ids),
        "rooms": len(room_ids),
        "bookings": len(bookings_data),
        "chat_sessions": len(sessions_data),
        "guests": len(guests_data),
        "audit_entries": len(audit_data),
        "knowledge_files": len(files_data),
        "metrics_rows": len(metrics_rows),
        "service_categories": seeded_service_categories,
        "service_partners": seeded_service_partners,
        "services": seeded_services,
        "service_bookings": seeded_service_bookings,
        "service_revenue_points": seeded_service_revenue_points,
        "property_ids": property_ids,
    }
