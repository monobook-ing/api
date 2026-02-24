-- Migration: Guest Manager schema extensions and session linkage backfill
-- Run this on existing databases that already have init_db.sql applied

-- Guests: profile fields for manager UI
ALTER TABLE guests
  ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

ALTER TABLE guests
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Chat sessions: link session to canonical guest entity
ALTER TABLE chat_sessions
  ADD COLUMN IF NOT EXISTS guest_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chat_sessions_guest_id_fkey'
  ) THEN
    ALTER TABLE chat_sessions
      ADD CONSTRAINT chat_sessions_guest_id_fkey
      FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE SET NULL;
  END IF;
END;
$$;

-- Backfill session.guest_id from booking conversation IDs first
WITH booking_guest AS (
  SELECT DISTINCT ON (property_id, conversation_id)
    property_id,
    conversation_id,
    guest_id
  FROM bookings
  WHERE conversation_id IS NOT NULL
    AND guest_id IS NOT NULL
  ORDER BY property_id, conversation_id, created_at DESC
)
UPDATE chat_sessions AS cs
SET
  guest_id = bg.guest_id,
  updated_at = NOW()
FROM booking_guest AS bg
WHERE cs.guest_id IS NULL
  AND cs.property_id = bg.property_id
  AND cs.id::TEXT = bg.conversation_id;

-- Fallback backfill by guest email (case-insensitive).
-- Only update when the session maps to exactly one candidate guest.
WITH email_candidates AS (
  SELECT
    cs.id AS session_id,
    g.id AS guest_id
  FROM chat_sessions AS cs
  JOIN guests AS g
    ON g.property_id = cs.property_id
  WHERE cs.guest_id IS NULL
    AND NULLIF(btrim(cs.guest_email), '') IS NOT NULL
    AND NULLIF(btrim(g.email), '') IS NOT NULL
    AND lower(btrim(cs.guest_email)) = lower(btrim(g.email))
),
matched_email AS (
  SELECT
    session_id,
    MIN(guest_id::TEXT)::UUID AS guest_id
  FROM email_candidates
  GROUP BY session_id
  HAVING COUNT(DISTINCT guest_id) = 1
)
UPDATE chat_sessions AS cs
SET
  guest_id = me.guest_id,
  updated_at = NOW()
FROM matched_email AS me
WHERE cs.id = me.session_id
  AND cs.guest_id IS NULL;

-- Final fallback backfill by guest name (case-insensitive).
-- Only update when the session maps to exactly one candidate guest.
WITH name_candidates AS (
  SELECT
    cs.id AS session_id,
    g.id AS guest_id
  FROM chat_sessions AS cs
  JOIN guests AS g
    ON g.property_id = cs.property_id
  WHERE cs.guest_id IS NULL
    AND NULLIF(btrim(cs.guest_name), '') IS NOT NULL
    AND NULLIF(btrim(g.name), '') IS NOT NULL
    AND lower(btrim(cs.guest_name)) = lower(btrim(g.name))
),
matched_name AS (
  SELECT
    session_id,
    MIN(guest_id::TEXT)::UUID AS guest_id
  FROM name_candidates
  GROUP BY session_id
  HAVING COUNT(DISTINCT guest_id) = 1
)
UPDATE chat_sessions AS cs
SET
  guest_id = mn.guest_id,
  updated_at = NOW()
FROM matched_name AS mn
WHERE cs.id = mn.session_id
  AND cs.guest_id IS NULL;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chat_sessions_guest ON chat_sessions(guest_id);
CREATE INDEX IF NOT EXISTS idx_guests_property_email_ci ON guests(property_id, lower(email));
CREATE INDEX IF NOT EXISTS idx_guests_property_name_ci ON guests(property_id, lower(name));
