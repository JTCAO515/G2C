-- local runtime only: explicitly installed canonical C formal Memory adapter.
-- No table/column/role/grant change. The existing initializer/table owner alone
-- may select this compatibility branch; the value grants no runtime authority.
CREATE OR REPLACE FUNCTION public.cj_message_trip_activation_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE compatible boolean;
BEGIN
 PERFORM 1 FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'formal Trip owner unavailable'; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_trip_profile WHERE scope=NEW.scope) THEN RETURN NEW; END IF;
 compatible:=current_setting('cj.formal_memory_consumer',true) IS NOT DISTINCT FROM 'CJ-MESSAGE-FORMAL-MEMORY@1'
  AND current_user=pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid='public.cj_message_trip_profile'::regclass));
 IF EXISTS(SELECT 1 FROM public.cj_message_delivery WHERE scope=NEW.scope AND NOT acknowledged)
 OR EXISTS(SELECT 1 FROM public.cj_run_record WHERE scope=NEW.scope AND status IN ('queued','running'))
 OR (EXISTS(SELECT 1 FROM public.cj_memory_scope WHERE scope=NEW.scope) AND NOT compatible) THEN
  RAISE EXCEPTION 'unresolved original work or unadapted MEMORY prevents formal Trip activation';
 END IF;
 RETURN NEW;
END $$;
