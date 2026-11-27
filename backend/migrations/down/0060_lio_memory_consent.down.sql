-- local runtime only: refuse to drop consent records (they are the audit trail of a privacy choice).
LOCK TABLE public.cj_lio_memory_consent IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_lio_memory_consent) THEN
  RAISE EXCEPTION 'lio_memory_consent down refused: retained private data';
 END IF;
END $$;
DROP TABLE public.cj_lio_memory_consent;
DROP FUNCTION public.cj_lio_memory_consent_reject_truncate();
DROP FUNCTION public.cj_lio_memory_consent_order();
