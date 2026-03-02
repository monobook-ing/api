-- Migration: RAG knowledge indexing + query logging
-- Run this on existing databases after init_db.sql.

-- ============================================================================
-- knowledge_files enrichments
-- ============================================================================
ALTER TABLE knowledge_files
  ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'en',
  ADD COLUMN IF NOT EXISTS doc_type TEXT DEFAULT 'general',
  ADD COLUMN IF NOT EXISTS effective_date DATE,
  ADD COLUMN IF NOT EXISTS indexing_status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

UPDATE knowledge_files
SET language = 'en'
WHERE language IS NULL;

UPDATE knowledge_files
SET doc_type = 'general'
WHERE doc_type IS NULL;

UPDATE knowledge_files
SET indexing_status = 'pending'
WHERE indexing_status IS NULL;

UPDATE knowledge_files
SET updated_at = NOW()
WHERE updated_at IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_files_doc_type_check'
  ) THEN
    ALTER TABLE knowledge_files
      ADD CONSTRAINT knowledge_files_doc_type_check
      CHECK (
        doc_type IN (
          'cancellation',
          'house_rules',
          'wifi',
          'faq',
          'amenities',
          'pricing',
          'general'
        )
      );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_files_indexing_status_check'
  ) THEN
    ALTER TABLE knowledge_files
      ADD CONSTRAINT knowledge_files_indexing_status_check
      CHECK (
        indexing_status IN ('pending', 'in_progress', 'indexed', 'error')
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_knowledge_files_indexing_status
  ON knowledge_files(indexing_status, created_at);

-- ============================================================================
-- rag_query_logs
-- ============================================================================
CREATE TABLE IF NOT EXISTS rag_query_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  chunks_used JSONB NOT NULL DEFAULT '[]'::jsonb,
  source TEXT NOT NULL DEFAULT 'chatgpt',
  language TEXT DEFAULT 'en',
  latency_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_query_logs_property_created
  ON rag_query_logs(property_id, created_at DESC);

-- ============================================================================
-- RPC: filtered embeddings search
-- ============================================================================
CREATE OR REPLACE FUNCTION match_embeddings_filtered(
  query_embedding vector(1536),
  match_property_id UUID,
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 10,
  match_source_type TEXT DEFAULT NULL,
  match_language TEXT DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  source_type TEXT,
  source_id UUID,
  content TEXT,
  similarity FLOAT,
  metadata JSONB
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.source_type::TEXT,
    e.source_id,
    e.content,
    (1 - (e.embedding <=> query_embedding))::FLOAT AS similarity,
    e.metadata
  FROM embeddings e
  WHERE e.property_id = match_property_id
    AND (match_source_type IS NULL OR e.source_type::TEXT = match_source_type)
    AND (
      match_language IS NULL
      OR COALESCE(e.metadata->>'language', '') = match_language
    )
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ============================================================================
-- RPC: claim next pending file with SKIP LOCKED semantics
-- ============================================================================
CREATE OR REPLACE FUNCTION claim_next_pending_knowledge_file()
RETURNS SETOF knowledge_files
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH next_file AS (
    SELECT kf.id
    FROM knowledge_files kf
    WHERE kf.indexing_status = 'pending'
      AND kf.deleted_at IS NULL
      AND kf.storage_path IS NOT NULL
    ORDER BY kf.created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
  )
  UPDATE knowledge_files kf
  SET indexing_status = 'in_progress',
      updated_at = NOW()
  FROM next_file
  WHERE kf.id = next_file.id
  RETURNING kf.*;
END;
$$;
