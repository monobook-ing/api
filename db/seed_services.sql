-- Seed: Services & Add-ons mock data
-- Idempotent seed that writes categories/partners at account scope and
-- services/bookings/analytics at property scope.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -------------------------------------------------------------------------
-- Account-scoped categories
-- -------------------------------------------------------------------------
WITH account_targets AS (
  SELECT DISTINCT p.account_id
  FROM properties p
),
category_seed AS (
  SELECT *
  FROM (
    VALUES
      ('spa-wellness', 'Spa & Wellness', 'Relaxation and body treatments', '🧖', 1),
      ('dining-drinks', 'Dining & Drinks', 'Restaurant and bar offerings', '🍽️', 2),
      ('activities', 'Activities', 'Tours, excursions, and entertainment', '🎯', 3),
      ('transport', 'Transport', 'Airport transfers and car rental', '🚗', 4),
      ('essentials', 'Essentials', 'Toiletries, chargers, and extras', '🧴', 5)
  ) AS v(slug, name, description, icon, sort_order)
)
INSERT INTO service_categories (
  account_id,
  slug,
  name,
  description,
  icon,
  sort_order
)
SELECT
  at.account_id,
  cs.slug,
  cs.name,
  cs.description,
  cs.icon,
  cs.sort_order
FROM account_targets at
CROSS JOIN category_seed cs
ON CONFLICT (account_id, slug)
DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  icon = EXCLUDED.icon,
  sort_order = EXCLUDED.sort_order,
  updated_at = NOW();

-- -------------------------------------------------------------------------
-- Account-scoped partners
-- -------------------------------------------------------------------------
WITH account_targets AS (
  SELECT DISTINCT p.account_id
  FROM properties p
),
partner_seed AS (
  SELECT *
  FROM (
    VALUES
      ('city-tours-ltd', 'City Tours Ltd.', 15.00, 'manual', 'active'),
      ('relax-spa-group', 'Relax Spa Group', 20.00, 'manual', 'active'),
      ('green-transfers', 'Green Transfers', 10.00, 'manual', 'inactive')
  ) AS v(slug, name, revenue_share_percent, payout_type, status)
)
INSERT INTO service_partners (
  account_id,
  slug,
  name,
  revenue_share_percent,
  payout_type,
  status
)
SELECT
  at.account_id,
  ps.slug,
  ps.name,
  ps.revenue_share_percent,
  ps.payout_type::service_partner_payout_type,
  ps.status::service_partner_status
FROM account_targets at
CROSS JOIN partner_seed ps
ON CONFLICT (account_id, slug)
DO UPDATE SET
  name = EXCLUDED.name,
  revenue_share_percent = EXCLUDED.revenue_share_percent,
  payout_type = EXCLUDED.payout_type,
  status = EXCLUDED.status,
  updated_at = NOW();

-- -------------------------------------------------------------------------
-- Property-scoped services
-- -------------------------------------------------------------------------
WITH property_targets AS (
  SELECT p.id AS property_id, p.account_id
  FROM properties p
),
service_seed AS (
  SELECT *
  FROM (
    VALUES
      (
        'deep-tissue-massage',
        'Deep Tissue Massage',
        '60-minute deep tissue massage in-room or spa',
        'A therapeutic full-body massage targeting muscle tension and stress relief. Available in-room or at the hotel spa.',
        ARRAY['https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=1200&h=800&fit=crop'],
        'internal',
        'spa-wellness',
        NULL,
        'active',
        'public',
        'fixed',
        89.00,
        'USD',
        20.00,
        TRUE,
        TRUE,
        'time_slot',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'any',
        10.00,
        'en',
        TRUE,
        24.00,
        187,
        5340.00,
        18.00
      ),
      (
        'airport-transfer',
        'Airport Transfer',
        'Private car transfer to/from airport',
        'Comfortable private sedan or minivan transfer between the hotel and the nearest airport. Book up to 24h before arrival.',
        ARRAY['https://images.unsplash.com/photo-1549317661-bd32c8ce0afa?w=1200&h=800&fit=crop'],
        'partner',
        'transport',
        'green-transfers',
        'active',
        'after_booking',
        'fixed',
        45.00,
        'USD',
        10.00,
        FALSE,
        TRUE,
        'linked_booking',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'any',
        NULL,
        'en',
        TRUE,
        38.00,
        312,
        8100.00,
        32.00
      ),
      (
        'romantic-dinner-package',
        'Romantic Dinner Package',
        '4-course dinner with wine pairing for two',
        'An exclusive candlelit 4-course dinner at the rooftop restaurant with curated wine pairing. Perfect for special occasions.',
        ARRAY['https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1200&h=800&fit=crop'],
        'internal',
        'dining-drinks',
        NULL,
        'active',
        'public',
        'per_person',
        120.00,
        'USD',
        20.00,
        TRUE,
        FALSE,
        'date_range',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'any',
        NULL,
        'en',
        TRUE,
        12.00,
        64,
        3840.00,
        9.00
      ),
      (
        'city-walking-tour',
        'City Walking Tour',
        'Guided 3-hour tour of Old Town highlights',
        'Explore the city''s top landmarks with a certified local guide. Includes skip-the-line museum entry and a coffee stop.',
        ARRAY['https://images.unsplash.com/photo-1569949381669-ecf31ae8f613?w=1200&h=800&fit=crop'],
        'partner',
        'activities',
        'city-tours-ltd',
        'draft',
        'public',
        'per_person',
        35.00,
        'USD',
        10.00,
        TRUE,
        TRUE,
        'time_slot',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'any',
        NULL,
        'en',
        TRUE,
        8.00,
        42,
        980.00,
        6.00
      ),
      (
        'premium-toiletry-kit',
        'Premium Toiletry Kit',
        'Luxury travel-size toiletry set',
        'Eco-friendly premium toiletry kit including shampoo, conditioner, body wash, and moisturizer in reusable containers.',
        ARRAY['https://images.unsplash.com/photo-1556228578-8c89e6adf883?w=1200&h=800&fit=crop'],
        'product',
        'essentials',
        NULL,
        'active',
        'during_stay',
        'fixed',
        25.00,
        'USD',
        20.00,
        FALSE,
        TRUE,
        'always',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        TRUE,
        'any',
        NULL,
        'en',
        TRUE,
        15.00,
        203,
        1525.00,
        12.00
      ),
      (
        'yoga-session',
        'Yoga Session',
        'Morning rooftop yoga class',
        'Start your day with a 45-minute guided yoga session on the rooftop terrace. Mats and water provided.',
        ARRAY['https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&h=800&fit=crop'],
        'internal',
        'spa-wellness',
        NULL,
        'hidden',
        'public',
        'per_person',
        20.00,
        'USD',
        20.00,
        TRUE,
        FALSE,
        'time_slot',
        'unlimited',
        NULL,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'any',
        NULL,
        'en',
        TRUE,
        20.00,
        156,
        2200.00,
        15.00
      )
  ) AS v(
    slug,
    name,
    short_description,
    full_description,
    image_urls,
    type,
    category_slug,
    partner_slug,
    status,
    visibility,
    pricing_type,
    price,
    currency_code,
    vat_percent,
    allow_discount,
    bundle_eligible,
    availability_type,
    capacity_mode,
    capacity_limit,
    recurring_schedule_enabled,
    available_before_booking,
    available_during_booking,
    post_booking_upsell,
    in_stay_qr_ordering,
    upsell_trigger_room_type,
    early_booking_discount_percent,
    knowledge_language,
    knowledge_ai_search_enabled,
    attach_rate,
    total_bookings,
    revenue_30d,
    conversion_rate
  )
),
resolved AS (
  SELECT
    pt.property_id,
    pt.account_id,
    ss.slug,
    ss.name,
    ss.short_description,
    ss.full_description,
    ss.image_urls,
    ss.type::service_type AS type,
    sc.id AS category_id,
    sp.id AS partner_id,
    ss.status::service_status AS status,
    ss.visibility::service_visibility AS visibility,
    ss.pricing_type::service_pricing_type AS pricing_type,
    ss.price,
    ss.currency_code,
    ss.vat_percent,
    ss.allow_discount,
    ss.bundle_eligible,
    ss.availability_type::service_availability_type AS availability_type,
    ss.capacity_mode::service_capacity_mode AS capacity_mode,
    ss.capacity_limit,
    ss.recurring_schedule_enabled,
    ss.available_before_booking,
    ss.available_during_booking,
    ss.post_booking_upsell,
    ss.in_stay_qr_ordering,
    ss.upsell_trigger_room_type,
    ss.early_booking_discount_percent,
    ss.knowledge_language,
    ss.knowledge_ai_search_enabled,
    ss.attach_rate,
    ss.total_bookings,
    ss.revenue_30d,
    ss.conversion_rate
  FROM property_targets pt
  CROSS JOIN service_seed ss
  LEFT JOIN service_categories sc
    ON sc.account_id = pt.account_id AND sc.slug = ss.category_slug
  LEFT JOIN service_partners sp
    ON sp.account_id = pt.account_id AND sp.slug = ss.partner_slug
)
INSERT INTO services (
  property_id,
  account_id,
  category_id,
  partner_id,
  slug,
  name,
  short_description,
  full_description,
  image_urls,
  type,
  status,
  visibility,
  pricing_type,
  price,
  currency_code,
  vat_percent,
  allow_discount,
  bundle_eligible,
  availability_type,
  capacity_mode,
  capacity_limit,
  recurring_schedule_enabled,
  available_before_booking,
  available_during_booking,
  post_booking_upsell,
  in_stay_qr_ordering,
  upsell_trigger_room_type,
  early_booking_discount_percent,
  knowledge_language,
  knowledge_ai_search_enabled,
  attach_rate,
  total_bookings,
  revenue_30d,
  conversion_rate
)
SELECT
  r.property_id,
  r.account_id,
  r.category_id,
  r.partner_id,
  r.slug,
  r.name,
  r.short_description,
  r.full_description,
  r.image_urls,
  r.type,
  r.status,
  r.visibility,
  r.pricing_type,
  r.price,
  r.currency_code,
  r.vat_percent,
  r.allow_discount,
  r.bundle_eligible,
  r.availability_type,
  r.capacity_mode,
  r.capacity_limit,
  r.recurring_schedule_enabled,
  r.available_before_booking,
  r.available_during_booking,
  r.post_booking_upsell,
  r.in_stay_qr_ordering,
  r.upsell_trigger_room_type,
  r.early_booking_discount_percent,
  r.knowledge_language,
  r.knowledge_ai_search_enabled,
  r.attach_rate,
  r.total_bookings,
  r.revenue_30d,
  r.conversion_rate
FROM resolved r
ON CONFLICT (property_id, slug)
DO UPDATE SET
  account_id = EXCLUDED.account_id,
  category_id = EXCLUDED.category_id,
  partner_id = EXCLUDED.partner_id,
  name = EXCLUDED.name,
  short_description = EXCLUDED.short_description,
  full_description = EXCLUDED.full_description,
  image_urls = EXCLUDED.image_urls,
  type = EXCLUDED.type,
  status = EXCLUDED.status,
  visibility = EXCLUDED.visibility,
  pricing_type = EXCLUDED.pricing_type,
  price = EXCLUDED.price,
  currency_code = EXCLUDED.currency_code,
  vat_percent = EXCLUDED.vat_percent,
  allow_discount = EXCLUDED.allow_discount,
  bundle_eligible = EXCLUDED.bundle_eligible,
  availability_type = EXCLUDED.availability_type,
  capacity_mode = EXCLUDED.capacity_mode,
  capacity_limit = EXCLUDED.capacity_limit,
  recurring_schedule_enabled = EXCLUDED.recurring_schedule_enabled,
  available_before_booking = EXCLUDED.available_before_booking,
  available_during_booking = EXCLUDED.available_during_booking,
  post_booking_upsell = EXCLUDED.post_booking_upsell,
  in_stay_qr_ordering = EXCLUDED.in_stay_qr_ordering,
  upsell_trigger_room_type = EXCLUDED.upsell_trigger_room_type,
  early_booking_discount_percent = EXCLUDED.early_booking_discount_percent,
  knowledge_language = EXCLUDED.knowledge_language,
  knowledge_ai_search_enabled = EXCLUDED.knowledge_ai_search_enabled,
  attach_rate = EXCLUDED.attach_rate,
  total_bookings = EXCLUDED.total_bookings,
  revenue_30d = EXCLUDED.revenue_30d,
  conversion_rate = EXCLUDED.conversion_rate,
  updated_at = NOW();

-- -------------------------------------------------------------------------
-- Time slots
-- -------------------------------------------------------------------------
WITH slot_seed AS (
  SELECT *
  FROM (
    VALUES
      ('deep-tissue-massage', '09:00', 2, 2, 1),
      ('deep-tissue-massage', '11:00', 2, 1, 2),
      ('deep-tissue-massage', '14:00', 2, 0, 3),
      ('deep-tissue-massage', '16:00', 2, 0, 4),
      ('city-walking-tour', '10:00', 12, 8, 1),
      ('city-walking-tour', '15:00', 12, 3, 2),
      ('yoga-session', '07:00', 10, 10, 1),
      ('yoga-session', '08:00', 10, 5, 2)
  ) AS v(service_slug, slot_time, capacity, booked, sort_order)
)
INSERT INTO service_time_slots (
  service_id,
  slot_time,
  capacity,
  booked,
  sort_order
)
SELECT
  s.id,
  ss.slot_time::time,
  ss.capacity,
  ss.booked,
  ss.sort_order
FROM services s
JOIN slot_seed ss
  ON ss.service_slug = s.slug
ON CONFLICT (service_id, slot_time)
DO UPDATE SET
  capacity = EXCLUDED.capacity,
  booked = EXCLUDED.booked,
  sort_order = EXCLUDED.sort_order;

-- -------------------------------------------------------------------------
-- Service bookings
-- -------------------------------------------------------------------------
WITH booking_seed AS (
  SELECT *
  FROM (
    VALUES
      ('sb-1', 'deep-tissue-massage', 'Anna Müller', '2026-02-28', 1, 89.00, 'confirmed'),
      ('sb-2', 'deep-tissue-massage', 'James Lee', '2026-02-27', 2, 178.00, 'confirmed'),
      ('sb-3', 'airport-transfer', 'Sophie Martin', '2026-02-26', 1, 45.00, 'pending'),
      ('sb-4', 'romantic-dinner-package', 'Carlos Rivera', '2026-02-25', 2, 240.00, 'confirmed'),
      ('sb-5', 'premium-toiletry-kit', 'Emily Wang', '2026-02-24', 3, 75.00, 'confirmed'),
      ('sb-6', 'city-walking-tour', 'Oliver Brown', '2026-02-23', 1, 35.00, 'cancelled'),
      ('sb-7', 'yoga-session', 'Yuki Tanaka', '2026-02-22', 1, 20.00, 'confirmed')
  ) AS v(external_ref, service_slug, guest_name, service_date, quantity, total, status)
)
INSERT INTO service_bookings (
  property_id,
  service_id,
  external_ref,
  guest_name,
  service_date,
  quantity,
  total,
  status
)
SELECT
  s.property_id,
  s.id,
  bs.external_ref,
  bs.guest_name,
  bs.service_date::date,
  bs.quantity,
  bs.total,
  bs.status::service_booking_status
FROM services s
JOIN booking_seed bs
  ON bs.service_slug = s.slug
ON CONFLICT (service_id, external_ref)
DO UPDATE SET
  guest_name = EXCLUDED.guest_name,
  service_date = EXCLUDED.service_date,
  quantity = EXCLUDED.quantity,
  total = EXCLUDED.total,
  status = EXCLUDED.status,
  updated_at = NOW();

-- -------------------------------------------------------------------------
-- Monthly revenue snapshots
-- -------------------------------------------------------------------------
WITH revenue_seed AS (
  SELECT *
  FROM (
    VALUES
      ('2025-09-01', 4200.00),
      ('2025-10-01', 5800.00),
      ('2025-11-01', 6100.00),
      ('2025-12-01', 8400.00),
      ('2026-01-01', 7200.00),
      ('2026-02-01', 9100.00)
  ) AS v(month, revenue)
),
property_targets AS (
  SELECT p.id AS property_id
  FROM properties p
)
INSERT INTO service_revenue_monthly (
  property_id,
  month,
  revenue
)
SELECT
  pt.property_id,
  rs.month::date,
  rs.revenue
FROM property_targets pt
CROSS JOIN revenue_seed rs
ON CONFLICT (property_id, month)
DO UPDATE SET
  revenue = EXCLUDED.revenue,
  updated_at = NOW();
