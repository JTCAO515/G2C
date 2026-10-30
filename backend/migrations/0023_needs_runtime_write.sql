-- local runtime only: explicit manual NEEDS profile; existing RLS/fence retained.
CREATE POLICY cj_needs_runtime_scope_insert ON public.cj_needs_scope FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_needs_runtime_record_insert ON public.cj_needs_record FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_needs_runtime_record_update ON public.cj_needs_record FOR UPDATE TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.needs_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_needs_runtime_revision_insert ON public.cj_needs_revision FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.needs_scope',true),''));
GRANT INSERT(scope) ON public.cj_needs_scope TO cj_m1_runtime;
GRANT INSERT(scope,needs_id,version,content),UPDATE(version,content) ON public.cj_needs_record TO cj_m1_runtime;
GRANT INSERT(scope,needs_id,version,action_id,operation,original_input,content,source_kind)
 ON public.cj_needs_revision TO cj_m1_runtime;
