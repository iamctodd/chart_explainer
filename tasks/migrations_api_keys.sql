-- ============================================================
-- ChartHawk: API Keys migration
-- Run this in the Supabase SQL Editor (Settings → SQL Editor)
-- ============================================================

CREATE TABLE IF NOT EXISTS public.api_keys (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name         text        NOT NULL DEFAULT 'My API key',
  key_hash     text        NOT NULL,
  key_prefix   text        NOT NULL,
  last_used_at timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Select: own keys" ON public.api_keys;
DROP POLICY IF EXISTS "Insert: own keys" ON public.api_keys;
DROP POLICY IF EXISTS "Delete: own keys" ON public.api_keys;

CREATE POLICY "Select: own keys" ON public.api_keys
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Insert: own keys" ON public.api_keys
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Delete: own keys" ON public.api_keys
  FOR DELETE USING (auth.uid() = user_id);
