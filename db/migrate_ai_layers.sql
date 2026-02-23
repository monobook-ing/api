-- Migration: Add AI/Vector/Chat tables (Layer 2 & 3)
-- Run this on existing databases that already have init_db.sql applied

-- New enums
CREATE TYPE ai_provider_type AS ENUM ('openai', 'claude', 'google');
CREATE TYPE chat_role AS ENUM ('user', 'assistant', 'system', 'tool');
CREATE TYPE embedding_source AS ENUM ('property', 'room', 'knowledge_chunk');

-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Alter knowledge_files: add content extraction fields
ALTER TABLE knowledge_files ADD COLUMN IF NOT EXISTS content_extracted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE knowledge_files ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE knowledge_files ADD COLUMN IF NOT EXISTS extraction_error TEXT;

-- AI provider connections
CREATE TABLE IF NOT EXISTS ai_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  provider ai_provider_type NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  api_key_encrypted TEXT,
  model_id TEXT,
  config JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (property_id, provider)
);

-- Chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  guest_name TEXT,
  guest_email TEXT,
  source audit_source_type NOT NULL DEFAULT 'widget',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role chat_role NOT NULL,
  content TEXT NOT NULL,
  tool_calls JSONB,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vector embeddings
CREATE TABLE IF NOT EXISTS embeddings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  source_type embedding_source NOT NULL,
  source_id UUID NOT NULL,
  chunk_index INTEGER NOT NULL DEFAULT 0,
  content TEXT NOT NULL,
  embedding vector(1536) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RPC function for cosine similarity search
CREATE OR REPLACE FUNCTION match_embeddings(
  query_embedding vector(1536),
  match_property_id UUID,
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 10
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
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_connections_property ON ai_connections(property_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_property ON chat_sessions(property_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_embeddings_property ON embeddings(property_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
