-- DRAFT r1 / #273: NOT IN MANIFEST; DO NOT EXECUTE BEFORE JT APPROVAL.
-- One approved migration-runner transaction, API/workers stopped. No CASCADE/data cleanup.
LOCK TABLE public.cj_run_scope,public.cj_run_record,public.cj_run_event,
 public.cj_message_scope,public.cj_message_chat,public.cj_message_receipt,
 public.cj_message_delivery,public.cj_message_draft,
 public.cj_travel_context,public.cj_travel_context_action,public.cj_message_context_profile,
 public.cj_message_travel_reference IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_travel_context)
 OR EXISTS(SELECT 1 FROM public.cj_travel_context_action)
 OR EXISTS(SELECT 1 FROM public.cj_message_context_profile)
 OR EXISTS(SELECT 1 FROM public.cj_message_travel_reference)
 OR EXISTS(SELECT 1 FROM public.cj_message_receipt WHERE travel_reference_version IS NOT NULL) THEN
   RAISE EXCEPTION 'travel context data/profile/reference exists; down refused';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint c
   WHERE c.contype='f' AND c.confrelid IN
    ('public.cj_travel_context'::regclass,'public.cj_travel_context_action'::regclass,
     'public.cj_message_context_profile'::regclass,
     'public.cj_message_travel_reference'::regclass)
   AND c.conrelid NOT IN
    ('public.cj_travel_context'::regclass,'public.cj_travel_context_action'::regclass,
     'public.cj_message_context_profile'::regclass,
     'public.cj_message_travel_reference'::regclass,'public.cj_message_receipt'::regclass)) THEN
   RAISE EXCEPTION 'external typed context FK exists; owner rollback approval required';
 END IF;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
   EXECUTE format('DROP POLICY cj_travel_consumer ON public.%I',t);
 END LOOP;
END $$;
DROP FUNCTION public.cj_message_travel_compatible(text);
DROP TRIGGER cj_message_travel_receipt ON public.cj_message_receipt;
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_message_travel_reference_required_fk;
DROP TABLE public.cj_message_travel_reference;
DROP TABLE public.cj_message_context_profile;
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_message_travel_origin_key;
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_message_travel_version_ck;
ALTER TABLE public.cj_message_receipt DROP COLUMN travel_reference_version;
ALTER TABLE public.cj_travel_context_action DROP CONSTRAINT cj_travel_action_identity_fk;
DROP TABLE public.cj_travel_context;
DROP TABLE public.cj_travel_context_action;
DROP FUNCTION public.cj_travel_context_guard();
DROP FUNCTION public.cj_travel_action_guard();
DROP FUNCTION public.cj_message_context_activation_guard();
DROP FUNCTION public.cj_message_travel_receipt_guard();
DROP FUNCTION public.cj_message_travel_epoch_guard();
DROP FUNCTION public.cj_message_travel_reference_guard();
-- All drops are RESTRICT by default; unknown external dependencies abort the whole transaction.
-- Existing 1–17 objects/data/policies/grants and all legacy raw bytes remain unchanged.
