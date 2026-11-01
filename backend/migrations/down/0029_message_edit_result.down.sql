-- local runtime only. Retained profiles/results forbid downgrade.
LOCK TABLE public.cj_message_edit_result_profile,public.cj_run_event IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_message_edit_result_profile)
 OR EXISTS(SELECT 1 FROM public.cj_run_event WHERE kind='result_committed')
 THEN RAISE EXCEPTION 'scoped result runtime contains data; down refused'; END IF;
END $$;
DROP TRIGGER cj_run_scoped_result_complete ON public.cj_run_event;
DROP FUNCTION public.cj_run_scoped_result_complete();
ALTER TABLE public.cj_run_event DROP CONSTRAINT cj_run_event_kind_check, DROP CONSTRAINT cj_run_event_check,
 ADD CONSTRAINT cj_run_event_kind_check CHECK(kind IN ('started','text_delta','effect_committed','completed','failed','cancelled','context_invalid','unknown','draft_outcome','budget_denied')),
 ADD CONSTRAINT cj_run_event_check CHECK(
 (kind IN ('text_delta','effect_committed') AND length(value)>0)
 OR (kind='draft_outcome' AND value IN ('validation_failed','provider_failed','provider_unknown','budget_exhausted'))
 OR (kind='budget_denied' AND value IN ('answer','draft'))
 OR (kind NOT IN ('text_delta','effect_committed','draft_outcome','budget_denied') AND value=''));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
  EXECUTE format('DROP POLICY cj_edit_result_consumer ON public.%I',t);
 END LOOP;
END $$;
DROP FUNCTION public.cj_message_edit_result_compatible(text);
DROP TABLE public.cj_message_edit_result_profile;
DROP FUNCTION public.cj_message_edit_result_activate();
