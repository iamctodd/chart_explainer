-- ============================================================
-- ChartHawk: Gallery, Sharing, Privacy & Comments migration
-- Run this in the Supabase SQL Editor (Settings → SQL Editor)
-- ============================================================

-- 1. Add public flag, gallery summary, and thumbnail to charts
ALTER TABLE public.charts
  ADD COLUMN IF NOT EXISTS is_public      boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS gallery_summary jsonb,
  ADD COLUMN IF NOT EXISTS thumbnail_data  text;

-- 2. Index for fast gallery feed pagination
CREATE INDEX IF NOT EXISTS idx_charts_public_created
  ON public.charts (is_public, created_at DESC)
  WHERE is_public = true;

-- 3. Charts RLS — drop old policies, recreate with full CRUD + public visibility
DROP POLICY IF EXISTS "Users can view their own charts"  ON public.charts;
DROP POLICY IF EXISTS "Select: own or public charts"     ON public.charts;
DROP POLICY IF EXISTS "Insert: own charts only"          ON public.charts;
DROP POLICY IF EXISTS "Update: own charts only"          ON public.charts;
DROP POLICY IF EXISTS "Delete: own charts only"          ON public.charts;

CREATE POLICY "Select: own or public charts" ON public.charts
  FOR SELECT USING (auth.uid() = user_id OR is_public = true);

CREATE POLICY "Insert: own charts only" ON public.charts
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Update: own charts only" ON public.charts
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Delete: own charts only" ON public.charts
  FOR DELETE USING (auth.uid() = user_id);

-- 4. Messages RLS — allow public chart messages to be read anonymously
DROP POLICY IF EXISTS "Users can view messages for their charts"       ON public.messages;
DROP POLICY IF EXISTS "Select: messages for own or public charts"      ON public.messages;

CREATE POLICY "Select: messages for own or public charts" ON public.messages
  FOR SELECT USING (
    chart_id IN (
      SELECT id FROM public.charts
      WHERE is_public = true OR user_id = auth.uid()
    )
  );

-- 5. Comments table
CREATE TABLE IF NOT EXISTS public.comments (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id    uuid        NOT NULL REFERENCES public.charts(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL REFERENCES auth.users(id)    ON DELETE CASCADE,
  author_name text,
  content     text        NOT NULL CHECK (char_length(content) BETWEEN 1 AND 1000),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;

-- 6. Comments RLS — drop then create (safe to re-run)
DROP POLICY IF EXISTS "Select: comments on public or own charts" ON public.comments;
DROP POLICY IF EXISTS "Insert: logged-in users"                  ON public.comments;
DROP POLICY IF EXISTS "Update: own comments"                     ON public.comments;
DROP POLICY IF EXISTS "Delete: own comments"                     ON public.comments;

CREATE POLICY "Select: comments on public or own charts" ON public.comments
  FOR SELECT USING (
    chart_id IN (
      SELECT id FROM public.charts
      WHERE is_public = true OR user_id = auth.uid()
    )
  );

CREATE POLICY "Insert: logged-in users" ON public.comments
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Update: own comments" ON public.comments
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Delete: own comments" ON public.comments
  FOR DELETE USING (auth.uid() = user_id);
