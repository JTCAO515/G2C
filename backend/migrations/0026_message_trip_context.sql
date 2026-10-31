-- local runtime only. Apply atomically with local API/workers stopped.
CREATE TABLE public.cj_message_trip_profile (
 scope text PRIMARY KEY REFERENCES public.cj_message_context_profile(scope) ON DELETE RESTRICT,
 version text NOT NULL CHECK(version='message-trip.1')
);
ALTER TABLE public.cj_message_receipt ADD COLUMN trip_reference_version smallint
 CHECK(trip_reference_version IS NULL OR trip_reference_version=1);
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_message_trip_origin_key
 UNIQUE(scope,message_id,run_id,trip_reference_version);
CREATE TABLE public.cj_message_trip_reference (
 scope text NOT NULL REFERENCES public.cj_message_trip_profile(scope) ON DELETE RESTRICT,
 message_id text NOT NULL, run_id text NOT NULL, conversation_id text NOT NULL,
 generation text NOT NULL, sequence bigint NOT NULL CHECK(sequence>0),
 input_sha256 text NOT NULL CHECK(input_sha256 ~ '^[0-9a-f]{64}$'),
 reference_version smallint NOT NULL CHECK(reference_version=1),
 selection text NOT NULL CHECK(octet_length(selection)<=16384),
 selection_epoch bigint NOT NULL CHECK(selection_epoch>0),
 source_content bytea CHECK(octet_length(source_content)<=1048576),
 content_sha256 text CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 CHECK((source_content IS NULL)=(content_sha256 IS NULL)),
 PRIMARY KEY(scope,message_id), UNIQUE(scope,run_id),
 UNIQUE(scope,message_id,reference_version), UNIQUE(scope,conversation_id,generation,sequence),
 FOREIGN KEY(scope,message_id,run_id,reference_version)
 REFERENCES public.cj_message_receipt(scope,message_id,run_id,trip_reference_version)
 DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(scope,conversation_id,generation)
 REFERENCES public.cj_message_chat(scope,conversation_id,generation) ON DELETE RESTRICT
);
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_message_trip_reference_required_fk
 FOREIGN KEY(scope,message_id,trip_reference_version)
 REFERENCES public.cj_message_trip_reference(scope,message_id,reference_version)
 DEFERRABLE INITIALLY DEFERRED;
CREATE FUNCTION public.cj_message_trip_activation_guard() RETURNS trigger
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
CREATE TRIGGER cj_message_trip_activate BEFORE INSERT ON public.cj_message_trip_profile
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_trip_activation_guard();
CREATE FUNCTION public.cj_message_trip_receipt_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF EXISTS(SELECT 1 FROM public.cj_message_trip_profile WHERE scope=NEW.scope) THEN
   -- Lexically after the old travel trigger. No old travel reference is fabricated.
   NEW.travel_reference_version:=NULL; NEW.trip_reference_version:=1;
  ELSIF NEW.trip_reference_version IS NOT NULL THEN
   RAISE EXCEPTION 'formal Trip producer not activated';
  END IF;
 ELSIF NEW.trip_reference_version IS DISTINCT FROM OLD.trip_reference_version THEN
  RAISE EXCEPTION 'immutable formal Trip receipt marker';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_trip_receipt BEFORE INSERT OR UPDATE ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_trip_receipt_guard();
CREATE FUNCTION public.cj_message_trip_epoch_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE previous record; receipt record; chat record;
BEGIN
 SELECT * INTO receipt FROM public.cj_message_receipt WHERE scope=NEW.scope AND message_id=NEW.message_id;
 IF NOT FOUND OR (NEW.run_id,NEW.conversation_id,NEW.generation,NEW.sequence,NEW.input_sha256,NEW.reference_version)
 IS DISTINCT FROM (receipt.run_id,receipt.conversation_id,receipt.generation,receipt.sequence,receipt.input_sha256,receipt.trip_reference_version) THEN
  RAISE EXCEPTION 'original formal Trip reference mismatch';
 END IF;
 SELECT * INTO chat FROM public.cj_message_chat
 WHERE scope=NEW.scope AND conversation_id=NEW.conversation_id AND generation=NEW.generation;
 IF NOT FOUND OR NOT chat.active OR chat.last_sequence<>NEW.sequence THEN
  RAISE EXCEPTION 'formal Trip reference has no matching head';
 END IF;
 SELECT selection,selection_epoch,sequence INTO previous FROM public.cj_message_trip_reference
 WHERE scope=NEW.scope AND conversation_id=NEW.conversation_id AND generation=NEW.generation
 ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND THEN NEW.selection_epoch:=NEW.sequence;
 ELSIF previous.sequence>=NEW.sequence THEN RAISE EXCEPTION 'formal Trip reference must append';
 ELSIF previous.selection=NEW.selection THEN NEW.selection_epoch:=previous.selection_epoch;
 ELSE NEW.selection_epoch:=NEW.sequence;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_trip_epoch BEFORE INSERT ON public.cj_message_trip_reference
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_trip_epoch_guard();
CREATE FUNCTION public.cj_message_trip_compatible(p_scope text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT p_scope=NULLIF(current_setting('cj.message_scope',true),'')
 AND (current_setting('cj.message_trip_abi',true)='MESSAGE-TRIP-CONSUMER@1'
 OR NOT EXISTS(SELECT 1 FROM public.cj_message_trip_profile p WHERE p.scope=p_scope))
$$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_trip_profile','cj_message_trip_reference'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',t);
  IF t='cj_message_trip_profile' THEN
   EXECUTE format('CREATE POLICY cj_trip_message_owner ON public.%I FOR SELECT TO cj_m1_runtime USING(scope=NULLIF(current_setting(''cj.message_scope'',true),''''))',t);
  ELSE
   EXECUTE format('CREATE POLICY cj_trip_message_owner ON public.%I TO cj_m1_runtime USING(scope=NULLIF(current_setting(''cj.message_scope'',true),'''') AND current_setting(''cj.message_trip_abi'',true)=''MESSAGE-TRIP-CONSUMER@1'') WITH CHECK(scope=NULLIF(current_setting(''cj.message_scope'',true),'''') AND current_setting(''cj.message_trip_abi'',true)=''MESSAGE-TRIP-CONSUMER@1'')',t);
  END IF;
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
  EXECUTE format('CREATE POLICY cj_trip_message_consumer ON public.%I AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_message_trip_compatible(scope)) WITH CHECK(public.cj_message_trip_compatible(scope))',t);
 END LOOP;
END $$;
GRANT SELECT ON public.cj_message_trip_profile TO cj_m1_runtime;
GRANT SELECT,INSERT ON public.cj_message_trip_reference TO cj_m1_runtime;
REVOKE ALL ON FUNCTION public.cj_message_trip_activation_guard(),public.cj_message_trip_receipt_guard(),
 public.cj_message_trip_epoch_guard(),public.cj_message_trip_compatible(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cj_message_trip_compatible(text) TO cj_m1_runtime;
-- No new role, DELETE/TRUNCATE, UPDATE on references, BYPASSRLS or SECURITY DEFINER.
