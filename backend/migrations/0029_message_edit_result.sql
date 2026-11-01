-- local runtime only. Apply atomically with local API/workers stopped.
CREATE TABLE public.cj_message_edit_result_profile (
 scope text PRIMARY KEY REFERENCES public.cj_message_scope(scope) ON DELETE RESTRICT,
 version text NOT NULL CHECK(version='message-edit-result.1')
);
ALTER TABLE public.cj_message_edit_result_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_message_edit_result_profile FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_edit_result_profile_owner ON public.cj_message_edit_result_profile
 FOR SELECT TO cj_m1_runtime USING(scope=NULLIF(current_setting('cj.message_scope',true),''));
GRANT SELECT ON public.cj_message_edit_result_profile TO cj_m1_runtime;
CREATE FUNCTION public.cj_message_edit_result_activate() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM 1 FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.cj_message_edit_profile WHERE scope=NEW.scope) THEN RAISE EXCEPTION 'original edit owner unavailable'; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_edit_result_profile WHERE scope=NEW.scope) THEN RETURN NEW; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_delivery WHERE scope=NEW.scope AND NOT acknowledged)
 OR EXISTS(SELECT 1 FROM public.cj_run_record WHERE scope=NEW.scope AND status IN ('queued','running'))
 THEN RAISE EXCEPTION 'unresolved original work prevents result activation'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_edit_result_activate BEFORE INSERT ON public.cj_message_edit_result_profile
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_edit_result_activate();
CREATE FUNCTION public.cj_message_edit_result_compatible(p_scope text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT p_scope=NULLIF(current_setting('cj.message_scope',true),'')
 AND (current_setting('cj.message_edit_result_abi',true)='CJ-MESSAGE-EDIT-RESULT@1'
 OR NOT EXISTS(SELECT 1 FROM public.cj_message_edit_result_profile p WHERE p.scope=p_scope))
$$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
  EXECUTE format('CREATE POLICY cj_edit_result_consumer ON public.%I AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_message_edit_result_compatible(scope)) WITH CHECK(public.cj_message_edit_result_compatible(scope))',t);
 END LOOP;
END $$;
ALTER TABLE public.cj_run_event DROP CONSTRAINT cj_run_event_kind_check, DROP CONSTRAINT cj_run_event_check,
 ADD CONSTRAINT cj_run_event_kind_check CHECK(kind IN ('started','text_delta','effect_committed','completed','failed','cancelled','context_invalid','unknown','draft_outcome','budget_denied','result_committed')),
 ADD CONSTRAINT cj_run_event_check CHECK(
 (kind IN ('text_delta','effect_committed') AND length(value)>0 AND (kind<>'effect_committed' OR value NOT LIKE 'scoped_result:%'))
 OR (kind='draft_outcome' AND value IN ('validation_failed','provider_failed','provider_unknown','budget_exhausted'))
 OR (kind='budget_denied' AND value IN ('answer','draft'))
 OR (kind='result_committed' AND value ~ '^scoped_result:(clarification_required|expansion_required):[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
 OR (kind NOT IN ('text_delta','effect_committed','draft_outcome','budget_denied','result_committed') AND value=''));
CREATE FUNCTION public.cj_run_scoped_result_complete() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NEW.kind<>'result_committed' THEN RETURN NEW; END IF;
 IF current_setting('cj.message_edit_result_abi',true) IS DISTINCT FROM 'CJ-MESSAGE-EDIT-RESULT@1'
 OR NOT EXISTS(SELECT 1 FROM public.cj_message_edit_result_profile WHERE scope=NEW.scope)
 OR NOT EXISTS(SELECT 1 FROM public.cj_run_record r JOIN public.cj_message_receipt m
 ON (m.scope,m.run_id)=(r.scope,r.run_id)
 WHERE r.scope=NEW.scope AND r.run_id=NEW.run_id AND r.status='completed'
 AND r.event_sequence=NEW.sequence+1 AND m.edit_reference_version=1)
 OR NOT EXISTS(SELECT 1 FROM public.cj_run_event WHERE scope=NEW.scope AND run_id=NEW.run_id
 AND sequence=NEW.sequence+1 AND kind='completed')
 OR (SELECT count(*) FROM public.cj_run_event WHERE scope=NEW.scope AND run_id=NEW.run_id AND kind='result_committed')<>1
 OR EXISTS(SELECT 1 FROM public.cj_run_event WHERE scope=NEW.scope AND run_id=NEW.run_id
 AND (kind IN ('draft_outcome','budget_denied') OR kind='effect_committed' AND value LIKE 'trip_proposal:%'))
 THEN RAISE EXCEPTION 'original scoped result must complete atomically'; END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER cj_run_scoped_result_complete AFTER INSERT ON public.cj_run_event
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.cj_run_scoped_result_complete();
REVOKE ALL ON FUNCTION public.cj_message_edit_result_activate(),public.cj_message_edit_result_compatible(text),public.cj_run_scoped_result_complete() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cj_message_edit_result_compatible(text) TO cj_m1_runtime;
-- No C result body table, new role, DELETE/TRUNCATE, BYPASSRLS or SECURITY DEFINER.
