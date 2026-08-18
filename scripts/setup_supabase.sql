-- ============================================================================
-- Supabase PostgreSQL Setup Script for Industrial Commerce Product AI Agent
-- ============================================================================
-- Execute this SQL in your Supabase SQL Editor (https://supabase.com/dashboard)
-- to create the `rag_products` table with unique constraint on (mpn, brand).
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mpn TEXT NOT NULL,
    brand TEXT NOT NULL,
    title TEXT,
    description TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_mpn_brand UNIQUE (mpn, brand)
);

-- Index for fast lookup by MPN and Brand
CREATE INDEX IF NOT EXISTS idx_rag_products_mpn_brand ON rag_products (mpn, brand);

-- Disable Row Level Security (RLS) for backend access or add permissive policy
ALTER TABLE rag_products DISABLE ROW LEVEL SECURITY;
