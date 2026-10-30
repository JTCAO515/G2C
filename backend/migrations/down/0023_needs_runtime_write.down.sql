-- local runtime only: never revoke the writer beneath retained NEEDS data.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_needs_scope) OR EXISTS(SELECT 1 FROM public.cj_needs_record)
    OR EXISTS(SELECT 1 FROM public.cj_needs_revision) THEN
  RAISE EXCEPTION 'NEEDS runtime contains data; down refused' USING ERRCODE='55000';
 END IF;
END $$;
REVOKE INSERT(scope) ON public.cj_needs_scope FROM cj_m1_runtime;
REVOKE INSERT(scope,needs_id,version,content),UPDATE(version,content) ON public.cj_needs_record FROM cj_m1_runtime;
REVOKE INSERT(scope,needs_id,version,action_id,operation,original_input,content,source_kind)
 ON public.cj_needs_revision FROM cj_m1_runtime;
DROP POLICY cj_needs_runtime_scope_insert ON public.cj_needs_scope;
DROP POLICY cj_needs_runtime_record_insert ON public.cj_needs_record;
DROP POLICY cj_needs_runtime_record_update ON public.cj_needs_record;
DROP POLICY cj_needs_runtime_revision_insert ON public.cj_needs_revision;
