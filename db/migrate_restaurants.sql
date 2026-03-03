-- Migration: Restaurant recommendations (curated + instant places)
-- Adds curated whitelist, analytics/moderation tables, and Google Places cache.

CREATE TABLE IF NOT EXISTS curated_places (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  google_place_id TEXT,
  name TEXT NOT NULL,
  address TEXT,
  lat DOUBLE PRECISION,
  lng DOUBLE PRECISION,
  cuisine TEXT[] NOT NULL DEFAULT '{}',
  price_level INTEGER CHECK (price_level BETWEEN 0 AND 4),
  rating NUMERIC(3,2),
  review_count INTEGER,
  phone TEXT,
  website TEXT,
  photo_urls TEXT[] NOT NULL DEFAULT '{}',
  opening_hours JSONB,
  meal_types TEXT[] NOT NULL DEFAULT '{}',
  tags TEXT[] NOT NULL DEFAULT '{}',
  best_for TEXT[] NOT NULL DEFAULT '{}',
  walking_minutes INTEGER,
  notes TEXT,
  sponsored BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_curated_places_property_google_unique
  ON curated_places(property_id, google_place_id)
  WHERE google_place_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_curated_places_property
  ON curated_places(property_id);

CREATE INDEX IF NOT EXISTS idx_curated_places_property_active
  ON curated_places(property_id, sponsored DESC, sort_order ASC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_curated_places_meal_types_gin
  ON curated_places USING GIN(meal_types);

CREATE INDEX IF NOT EXISTS idx_curated_places_tags_gin
  ON curated_places USING GIN(tags);

CREATE TABLE IF NOT EXISTS place_clicks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  place_id TEXT NOT NULL,
  place_source TEXT NOT NULL,
  context TEXT,
  session_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_place_clicks_property_created
  ON place_clicks(property_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_place_clicks_place
  ON place_clicks(place_id, place_source);

CREATE TABLE IF NOT EXISTS place_issues (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  place_id TEXT NOT NULL,
  place_source TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  comment TEXT,
  session_id TEXT,
  resolved BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_place_issues_property_created
  ON place_issues(property_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_place_issues_resolved
  ON place_issues(property_id, resolved);

CREATE TABLE IF NOT EXISTS places_cache (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  cache_key TEXT NOT NULL UNIQUE,
  response_data JSONB NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_places_cache_expires_at
  ON places_cache(expires_at);
