-- local runtime only. Never remove an ABI fence beneath retained data.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_message_edit_profile)
 OR EXISTS(SELECT 1 FROM public.cj_message_edit_reference)
 OR EXISTS(SELECT 1 FROM public.cj_message_receipt WHERE edit_reference_version IS NOT NULL) THEN
  RAISE EXCEPTION 'formal Trip runtime contains data; down refused';
 END IF;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
  EXECUTE format('DROP POLICY cj_edit_message_consumer ON public.%I',t);
 END LOOP;
END $$;
DROP FUNCTION public.cj_message_edit_compatible(text);
DROP TRIGGER cj_message_z_edit_receipt ON public.cj_message_receipt;
DROP TRIGGER cj_message_edit_activate ON public.cj_message_edit_profile;
DROP TRIGGER cj_message_edit_epoch ON public.cj_message_edit_reference;
DROP FUNCTION public.cj_message_edit_receipt_guard(),public.cj_message_edit_activation_guard(),public.cj_message_edit_epoch_guard();
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_message_edit_reference_required_fk;
DROP TABLE public.cj_message_edit_reference;
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_message_edit_origin_key;
ALTER TABLE public.cj_message_receipt DROP COLUMN edit_reference_version;
DROP TABLE public.cj_message_edit_profile;
