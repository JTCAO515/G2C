-- local runtime only: refuse to drop Trip origin, tombstone or commit time records while any row exists
-- (they are the audit trail of automatic saves and of what the person removed).
LOCK TABLE public.cj_trip_item_origin,public.cj_trip_item_tombstone,public.cj_trip_commit_time IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_trip_item_origin) OR EXISTS(SELECT 1 FROM public.cj_trip_item_tombstone)
    OR EXISTS(SELECT 1 FROM public.cj_trip_commit_time) THEN
  RAISE EXCEPTION 'trip_autosave down refused: retained private data';
 END IF;
END $$;
DROP TABLE public.cj_trip_commit_time;
DROP TABLE public.cj_trip_item_tombstone;
DROP TABLE public.cj_trip_item_origin;
DROP FUNCTION public.cj_trip_autosave_append_only();
DROP FUNCTION public.cj_trip_commit_time_order();
DROP FUNCTION public.cj_trip_item_tombstone_order();
DROP FUNCTION public.cj_trip_item_origin_order();
