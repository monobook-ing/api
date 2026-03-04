-- Migration: split tenant account from property records
-- - Accounts become tenants/organizations
-- - Properties store their own name
-- - One account can own multiple properties

ALTER TABLE properties
  ADD COLUMN IF NOT EXISTS name TEXT;

-- Backfill property names from account names for existing rows
UPDATE properties AS p
SET name = COALESCE(NULLIF(btrim(a.name), ''), 'My Property')
FROM accounts AS a
WHERE p.account_id = a.id
  AND (p.name IS NULL OR btrim(p.name) = '');

-- Ensure no blank names remain before setting NOT NULL
UPDATE properties
SET name = 'My Property'
WHERE name IS NULL OR btrim(name) = '';

-- Create default properties for accounts that currently have none
INSERT INTO properties (account_id, name)
SELECT
  a.id,
  COALESCE(NULLIF(btrim(a.name), ''), 'My Property')
FROM accounts AS a
LEFT JOIN properties AS p
  ON p.account_id = a.id
WHERE p.id IS NULL;

ALTER TABLE properties
  ALTER COLUMN name SET NOT NULL;

-- Remove 1:1 account<->property uniqueness so accounts can own many properties
ALTER TABLE properties
  DROP CONSTRAINT IF EXISTS properties_account_id_key;
