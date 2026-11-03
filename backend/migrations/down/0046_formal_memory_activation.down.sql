-- local runtime only: preserve scopes requiring explicit installed compatibility.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_message_trip_profile p JOIN public.cj_memory_scope m USING(scope)) THEN
  RAISE EXCEPTION 'compatible formal Memory scopes retained';
 END IF;
END $$;
CREATE OR REPLACE FUNCTION public.cj_message_trip_activation_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM 1 FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'formal Trip owner unavailable'; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_trip_profile WHERE scope=NEW.scope) THEN RETURN NEW; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_delivery WHERE scope=NEW.scope AND NOT acknowledged)
 OR EXISTS(SELECT 1 FROM public.cj_run_record WHERE scope=NEW.scope AND status IN ('queued','running'))
 OR EXISTS(SELECT 1 FROM public.cj_memory_scope WHERE scope=NEW.scope) THEN
  RAISE EXCEPTION 'unresolved original work or unadapted MEMORY prevents formal Trip activation';
 END IF;
 RETURN NEW;
END $$;
