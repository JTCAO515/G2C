LOCK TABLE public.cj_native4_usage_profile,public.cj_usage_ledger_candidate IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_native4_usage_profile)
   OR EXISTS(SELECT 1 FROM public.cj_usage_ledger_candidate WHERE format_version=2)
 THEN RAISE EXCEPTION 'native4 original accounting requires version-2 reader; down refused'; END IF;
END $$;
DROP TABLE public.cj_native4_usage_profile;
ALTER TABLE public.cj_usage_ledger_candidate DROP CONSTRAINT cj_usage_ledger_candidate_format_version_check;
ALTER TABLE public.cj_usage_ledger_candidate ADD CONSTRAINT cj_usage_ledger_candidate_format_version_check
 CHECK(format_version=1);
