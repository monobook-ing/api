-- Migration: Services & Add-ons schema
-- Adds service catalogs, partners, services, slots, service bookings, and analytics snapshots.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_type') THEN
    CREATE TYPE service_type AS ENUM ('internal', 'partner', 'product');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_status') THEN
    CREATE TYPE service_status AS ENUM ('active', 'hidden', 'draft');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_pricing_type') THEN
    CREATE TYPE service_pricing_type AS ENUM ('fixed', 'per_person', 'per_night', 'per_hour', 'dynamic');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_availability_type') THEN
    CREATE TYPE service_availability_type AS ENUM ('always', 'date_range', 'time_slot', 'linked_booking');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_visibility') THEN
    CREATE TYPE service_visibility AS ENUM ('public', 'after_booking', 'during_stay');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_capacity_mode') THEN
    CREATE TYPE service_capacity_mode AS ENUM ('unlimited', 'limited_quantity', 'per_day_limit', 'per_hour_limit');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_partner_status') THEN
    CREATE TYPE service_partner_status AS ENUM ('active', 'inactive');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_partner_payout_type') THEN
    CREATE TYPE service_partner_payout_type AS ENUM ('manual', 'automated', 'affiliate');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'service_booking_status') THEN
    CREATE TYPE service_booking_status AS ENUM ('confirmed', 'pending', 'cancelled');
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS service_categories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  icon TEXT NOT NULL DEFAULT '📦',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (account_id, slug)
);

CREATE TABLE IF NOT EXISTS service_partners (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  revenue_share_percent NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (revenue_share_percent >= 0 AND revenue_share_percent <= 100),
  payout_type service_partner_payout_type NOT NULL DEFAULT 'manual',
  external_url TEXT,
  attribution_tracking BOOLEAN NOT NULL DEFAULT FALSE,
  status service_partner_status NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (account_id, slug)
);

CREATE TABLE IF NOT EXISTS services (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  category_id UUID REFERENCES service_categories(id) ON DELETE SET NULL,
  partner_id UUID REFERENCES service_partners(id) ON DELETE SET NULL,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  short_description TEXT NOT NULL DEFAULT '',
  full_description TEXT NOT NULL DEFAULT '',
  image_urls TEXT[] NOT NULL DEFAULT '{}',
  type service_type NOT NULL DEFAULT 'internal',
  status service_status NOT NULL DEFAULT 'draft',
  visibility service_visibility NOT NULL DEFAULT 'public',
  pricing_type service_pricing_type NOT NULL DEFAULT 'fixed',
  price NUMERIC(10,2) NOT NULL DEFAULT 0,
  currency_code TEXT NOT NULL DEFAULT 'USD' REFERENCES currencies(code),
  vat_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
  allow_discount BOOLEAN NOT NULL DEFAULT FALSE,
  bundle_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  availability_type service_availability_type NOT NULL DEFAULT 'always',
  capacity_mode service_capacity_mode NOT NULL DEFAULT 'unlimited',
  capacity_limit INTEGER,
  recurring_schedule_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  available_before_booking BOOLEAN NOT NULL DEFAULT TRUE,
  available_during_booking BOOLEAN NOT NULL DEFAULT TRUE,
  post_booking_upsell BOOLEAN NOT NULL DEFAULT FALSE,
  in_stay_qr_ordering BOOLEAN NOT NULL DEFAULT FALSE,
  upsell_trigger_room_type TEXT NOT NULL DEFAULT 'any',
  early_booking_discount_percent NUMERIC(5,2),
  knowledge_language TEXT NOT NULL DEFAULT 'en',
  knowledge_ai_search_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  attach_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
  total_bookings INTEGER NOT NULL DEFAULT 0,
  revenue_30d NUMERIC(12,2) NOT NULL DEFAULT 0,
  conversion_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (property_id, slug)
);

CREATE TABLE IF NOT EXISTS service_time_slots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  slot_time TIME NOT NULL,
  capacity INTEGER NOT NULL DEFAULT 0 CHECK (capacity >= 0),
  booked INTEGER NOT NULL DEFAULT 0 CHECK (booked >= 0),
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (service_id, slot_time)
);

CREATE TABLE IF NOT EXISTS service_bookings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
  external_ref TEXT NOT NULL,
  guest_name TEXT NOT NULL,
  service_date DATE NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  total NUMERIC(10,2) NOT NULL CHECK (total >= 0),
  currency_code TEXT NOT NULL DEFAULT 'USD' REFERENCES currencies(code),
  status service_booking_status NOT NULL DEFAULT 'confirmed',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (service_id, external_ref)
);

CREATE TABLE IF NOT EXISTS service_revenue_monthly (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  month DATE NOT NULL,
  revenue NUMERIC(12,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (property_id, month)
);

CREATE INDEX IF NOT EXISTS idx_service_categories_account ON service_categories(account_id);
CREATE INDEX IF NOT EXISTS idx_service_partners_account ON service_partners(account_id);
CREATE INDEX IF NOT EXISTS idx_services_property ON services(property_id);
CREATE INDEX IF NOT EXISTS idx_services_account ON services(account_id);
CREATE INDEX IF NOT EXISTS idx_services_category ON services(category_id);
CREATE INDEX IF NOT EXISTS idx_services_partner ON services(partner_id);
CREATE INDEX IF NOT EXISTS idx_services_status ON services(status);
CREATE INDEX IF NOT EXISTS idx_service_slots_service ON service_time_slots(service_id);
CREATE INDEX IF NOT EXISTS idx_service_bookings_property ON service_bookings(property_id);
CREATE INDEX IF NOT EXISTS idx_service_bookings_service ON service_bookings(service_id);
CREATE INDEX IF NOT EXISTS idx_service_bookings_date ON service_bookings(service_date DESC);
CREATE INDEX IF NOT EXISTS idx_service_revenue_monthly_property ON service_revenue_monthly(property_id, month);
