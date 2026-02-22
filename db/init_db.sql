CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enums (existing) ---------------------------------------------------------
CREATE TYPE user_role AS ENUM ('superadmin', 'brand', 'admin', 'creator');
CREATE TYPE team_member_status AS ENUM ('invited', 'accepted', 'rejected');
CREATE TYPE notification_type AS ENUM ('welcome', 'news', 'updates', 'invite_accepted');

-- Enums (new) --------------------------------------------------------------
CREATE TYPE booking_status AS ENUM ('confirmed', 'pending', 'ai_pending', 'cancelled');
CREATE TYPE room_source AS ENUM ('airbnb', 'booking', 'manual');
CREATE TYPE room_status AS ENUM ('active', 'draft', 'archived');
CREATE TYPE audit_source_type AS ENUM ('mcp', 'chatgpt', 'claude', 'gemini', 'widget');
CREATE TYPE audit_entry_status AS ENUM ('success', 'error', 'pending');
CREATE TYPE payment_provider_type AS ENUM ('stripe', 'jpmorgan', 'ipay', 'liqpay', 'monobank');
CREATE TYPE pms_provider_type AS ENUM ('mews', 'cloudbeds', 'servio');

-- ===========================================================================
-- Core tables (existing)
-- ===========================================================================

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email TEXT NOT NULL UNIQUE,
  first_name TEXT NOT NULL,
  last_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL
);

-- Accounts = Properties (one account per property)
CREATE TABLE accounts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE team_members (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role user_role NOT NULL DEFAULT 'admin',
  status team_member_status NOT NULL DEFAULT 'accepted',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  joined_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL,
  UNIQUE (account_id, user_id)
);

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  type notification_type NOT NULL DEFAULT 'welcome',
  details TEXT,
  cta TEXT,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE magic_tokens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  token TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- Property / Hotel domain tables (new)
-- ===========================================================================

-- Property details extend the accounts table (account = property)
CREATE TABLE properties (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_id UUID NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,

  -- Address
  street TEXT,
  city TEXT,
  state TEXT,
  postal_code TEXT,
  country TEXT,
  lat DOUBLE PRECISION,
  lng DOUBLE PRECISION,
  floor TEXT,
  section TEXT,
  property_number TEXT,

  -- Guest-facing info (shown in widget / AI)
  description TEXT,
  image_url TEXT,
  rating NUMERIC(3,2) DEFAULT 0,
  ai_match_score INTEGER DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Host profile per property (settings page)
CREATE TABLE host_profiles (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL UNIQUE REFERENCES properties(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  avatar_url TEXT,
  avatar_initials TEXT DEFAULT 'HO',
  reviews INTEGER NOT NULL DEFAULT 0,
  rating NUMERIC(3,2) NOT NULL DEFAULT 0,
  years_hosting INTEGER NOT NULL DEFAULT 0,
  superhost BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rooms
CREATE TABLE rooms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  images TEXT[] NOT NULL DEFAULT '{}',
  price_per_night NUMERIC(10,2) NOT NULL,
  max_guests INTEGER NOT NULL DEFAULT 2,
  bed_config TEXT NOT NULL DEFAULT '',
  amenities TEXT[] NOT NULL DEFAULT '{}',
  source room_source NOT NULL DEFAULT 'manual',
  source_url TEXT,
  sync_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  last_synced TIMESTAMPTZ,
  status room_status NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Room pricing: date overrides
CREATE TABLE room_date_pricing (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  UNIQUE (room_id, date)
);

-- Room pricing: guest tiers
CREATE TABLE room_guest_tiers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  min_guests INTEGER NOT NULL,
  max_guests INTEGER NOT NULL,
  price_per_night NUMERIC(10,2) NOT NULL
);

-- Guests (external people who book)
CREATE TABLE guests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bookings
CREATE TABLE bookings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  guest_id UUID NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
  check_in DATE NOT NULL,
  check_out DATE NOT NULL,
  total_price NUMERIC(10,2) NOT NULL,
  status booking_status NOT NULL DEFAULT 'pending',
  ai_handled BOOLEAN NOT NULL DEFAULT FALSE,
  source audit_source_type,
  conversation_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  cancelled_at TIMESTAMPTZ,
  CONSTRAINT check_dates CHECK (check_out > check_in)
);

-- Audit log for API / tool calls
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  conversation_id TEXT,
  source audit_source_type NOT NULL,
  tool_name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status audit_entry_status NOT NULL DEFAULT 'success',
  request_payload JSONB,
  response_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Knowledge-base files
CREATE TABLE knowledge_files (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  size TEXT NOT NULL DEFAULT '0 KB',
  storage_path TEXT,
  mime_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

-- PMS sync settings per property
CREATE TABLE pms_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  provider pms_provider_type NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  config JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (property_id, provider)
);

-- Payment provider settings per property
CREATE TABLE payment_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  provider payment_provider_type NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  config JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (property_id, provider)
);

-- Dashboard metrics snapshots (daily aggregate per property)
CREATE TABLE dashboard_metrics (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  ai_direct_bookings INTEGER NOT NULL DEFAULT 0,
  commission_saved NUMERIC(10,2) NOT NULL DEFAULT 0,
  occupancy_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
  revenue NUMERIC(12,2) NOT NULL DEFAULT 0,
  UNIQUE (property_id, date)
);

-- ===========================================================================
-- Indexes
-- ===========================================================================
CREATE INDEX idx_rooms_property ON rooms(property_id);
CREATE INDEX idx_bookings_property ON bookings(property_id);
CREATE INDEX idx_bookings_room ON bookings(room_id);
CREATE INDEX idx_bookings_dates ON bookings(check_in, check_out);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_audit_log_property ON audit_log(property_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_source ON audit_log(source);
CREATE INDEX idx_guests_property ON guests(property_id);
CREATE INDEX idx_knowledge_files_property ON knowledge_files(property_id);
CREATE INDEX idx_dashboard_metrics_property_date ON dashboard_metrics(property_id, date);
CREATE INDEX idx_properties_account ON properties(account_id);
