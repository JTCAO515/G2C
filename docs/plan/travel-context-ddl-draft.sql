-- DRAFT r1 / #273: NOT IN MANIFEST; DO NOT EXECUTE BEFORE JT APPROVAL.
-- Proposed append-only migration; number assigned from the latest manifest later.
-- Run only via one transaction of the approved migration runner, with API/workers stopped.
-- This file has NOT been parsed/executed against PostgreSQL.

CREATE TABLE public.cj_travel_context_action (
 scope text NOT NULL,
 action_id text NOT NULL CHECK (length(action_id) BETWEEN 1 AND 96),
 operation text NOT NULL CHECK (operation IN ('create','advance','deactivate')),
 context_id text NOT NULL CHECK (context_id ~ '^[0-9a-f]{32}$'),
 expected_version bigint,
 result_version bigint NOT NULL CHECK (result_version > 0),
 result_active boolean NOT NULL,
 original_input bytea NOT NULL,
 original_receipt bytea NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,action_id),
 UNIQUE(scope,context_id,result_version),
 UNIQUE(scope,context_id,result_version,result_active,action_id),
 CHECK ((operation='create' AND expected_version IS NULL AND result_version=1 AND result_active)
     OR (operation='advance' AND expected_version IS NOT NULL AND expected_version>0
         AND result_version-1=expected_version AND result_active)
     OR (operation='deactivate' AND expected_version IS NOT NULL AND expected_version>0
         AND result_version-1=expected_version AND NOT result_active)),
 FOREIGN KEY(scope,context_id,expected_version)
   REFERENCES public.cj_travel_context_action(scope,context_id,result_version)
   DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.cj_travel_context (
 scope text NOT NULL REFERENCES public.cj_message_scope(scope) ON DELETE RESTRICT,
 context_id text NOT NULL CHECK (context_id ~ '^[0-9a-f]{32}$'),
 version bigint NOT NULL CHECK (version>0),
 active boolean NOT NULL,
 head_action_id text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,context_id),
 FOREIGN KEY(scope,context_id,version,active,head_action_id)
   REFERENCES public.cj_travel_context_action(scope,context_id,result_version,result_active,action_id)
   DEFERRABLE INITIALLY DEFERRED
);
ALTER TABLE public.cj_travel_context_action ADD CONSTRAINT cj_travel_action_identity_fk
 FOREIGN KEY(scope,context_id) REFERENCES public.cj_travel_context(scope,context_id)
 DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE public.cj_message_context_profile (
 scope text PRIMARY KEY REFERENCES public.cj_local_metered_profile(scope) ON DELETE RESTRICT,
 version text NOT NULL CHECK (version='message-travel.1')
);
-- Old rows remain NULL, no rewriting or reinterpreting old raw bytes.
ALTER TABLE public.cj_message_receipt ADD COLUMN travel_reference_version smallint;
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_message_travel_version_ck
 CHECK (travel_reference_version IS NULL OR travel_reference_version=1);
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_message_travel_origin_key
 UNIQUE(scope,message_id,run_id,travel_reference_version);
CREATE TABLE public.cj_message_travel_reference (
 scope text NOT NULL REFERENCES public.cj_message_context_profile(scope) ON DELETE RESTRICT,
 message_id text NOT NULL,
 run_id text NOT NULL,
 conversation_id text NOT NULL,
 generation text NOT NULL,
 sequence bigint NOT NULL CHECK (sequence>0),
 input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
 reference_version smallint NOT NULL CHECK (reference_version=1),
 message_version text NOT NULL CHECK (message_version='MESSAGE-send.2'),
 reference_kind text NOT NULL CHECK (reference_kind IN ('none','travel')),
 context_id text,
 context_version bigint,
 selection_epoch bigint NOT NULL CHECK (selection_epoch>0),
 PRIMARY KEY(scope,message_id), UNIQUE(scope,run_id),
 UNIQUE(scope,message_id,reference_version),
 UNIQUE(scope,conversation_id,generation,sequence),
 CHECK ((reference_kind='none' AND context_id IS NULL AND context_version IS NULL)
     OR (reference_kind='travel' AND context_id IS NOT NULL AND context_version IS NOT NULL AND context_version>0)),
 FOREIGN KEY(scope,message_id,run_id,reference_version)
   REFERENCES public.cj_message_receipt(scope,message_id,run_id,travel_reference_version)
   DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(scope,conversation_id,generation)
   REFERENCES public.cj_message_chat(scope,conversation_id,generation) ON DELETE RESTRICT,
 FOREIGN KEY(scope,context_id) REFERENCES public.cj_travel_context(scope,context_id) ON DELETE RESTRICT,
 FOREIGN KEY(scope,context_id,context_version)
   REFERENCES public.cj_travel_context_action(scope,context_id,result_version) ON DELETE RESTRICT
);
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_message_travel_reference_required_fk
 FOREIGN KEY(scope,message_id,travel_reference_version)
 REFERENCES public.cj_message_travel_reference(scope,message_id,reference_version)
 DEFERRABLE INITIALLY DEFERRED;
CREATE FUNCTION public.cj_travel_context_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.version<>1 OR NOT NEW.active THEN RAISE EXCEPTION 'invalid initial travel state'; END IF;
 ELSE
   IF (NEW.scope,NEW.context_id,NEW.created_at) IS DISTINCT FROM (OLD.scope,OLD.context_id,OLD.created_at)
      OR NOT OLD.active OR NEW.version-1<>OLD.version OR NEW.head_action_id=OLD.head_action_id THEN
     RAISE EXCEPTION 'invalid travel transition';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_travel_context_state BEFORE INSERT OR UPDATE ON public.cj_travel_context
 FOR EACH ROW EXECUTE FUNCTION public.cj_travel_context_guard();
CREATE FUNCTION public.cj_travel_action_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE current_version bigint;
BEGIN
 SELECT version INTO current_version FROM public.cj_travel_context
 WHERE scope=NEW.scope AND context_id=NEW.context_id;
 IF NOT FOUND OR current_version<NEW.result_version THEN RAISE EXCEPTION 'travel action has no committed state'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER cj_travel_action_consistent AFTER INSERT ON public.cj_travel_context_action
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.cj_travel_action_guard();

CREATE FUNCTION public.cj_message_context_activation_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM 1 FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'context owner scope unavailable'; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_context_profile WHERE scope=NEW.scope) THEN RETURN NEW; END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_delivery WHERE scope=NEW.scope AND NOT acknowledged)
    OR EXISTS(SELECT 1 FROM public.cj_run_record WHERE scope=NEW.scope AND status IN ('queued','running')) THEN
   RAISE EXCEPTION 'unresolved original work prevents context activation';
 END IF;
 -- Ordinary RUN read only: never take a RUN write lock while holding MESSAGE.
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_context_activate BEFORE INSERT ON public.cj_message_context_profile
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_context_activation_guard();

CREATE FUNCTION public.cj_message_travel_receipt_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE enabled boolean;
BEGIN
 SELECT EXISTS(SELECT 1 FROM public.cj_message_context_profile WHERE scope=NEW.scope) INTO enabled;
 IF TG_OP='INSERT' THEN
   IF enabled THEN
     NEW.travel_reference_version:=1;
   ELSIF NEW.travel_reference_version IS NOT NULL THEN
     RAISE EXCEPTION 'travel producer is not activated';
   END IF;
 ELSE
   IF NEW.travel_reference_version IS DISTINCT FROM OLD.travel_reference_version THEN
     RAISE EXCEPTION 'immutable receipt protocol marker';
   END IF;
   IF (enabled OR OLD.travel_reference_version IS NOT NULL) AND
      (NEW.scope,NEW.message_id,NEW.conversation_id,NEW.generation,NEW.sequence,NEW.run_id,NEW.input_sha256,NEW.raw_input)
      IS DISTINCT FROM
      (OLD.scope,OLD.message_id,OLD.conversation_id,OLD.generation,OLD.sequence,OLD.run_id,OLD.input_sha256,OLD.raw_input) THEN
     RAISE EXCEPTION 'immutable original context message';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_travel_receipt BEFORE INSERT OR UPDATE ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_travel_receipt_guard();

-- Immutable ordered references are also the selection history; no second mutable selector store.
-- The unique (scope,conversation_id,generation,sequence) index supports backward latest reads.
CREATE FUNCTION public.cj_message_travel_epoch_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE previous record;
BEGIN
 SELECT reference_kind,context_id,context_version,selection_epoch,sequence INTO previous
 FROM public.cj_message_travel_reference WHERE scope=NEW.scope
 AND conversation_id=NEW.conversation_id AND generation=NEW.generation
 ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND THEN NEW.selection_epoch:=NEW.sequence;
 ELSIF previous.sequence>=NEW.sequence THEN RAISE EXCEPTION 'context reference must append';
 ELSIF (previous.reference_kind,previous.context_id,previous.context_version)
       IS NOT DISTINCT FROM (NEW.reference_kind,NEW.context_id,NEW.context_version) THEN
   NEW.selection_epoch:=previous.selection_epoch;
 ELSE NEW.selection_epoch:=NEW.sequence;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_message_travel_epoch BEFORE INSERT ON public.cj_message_travel_reference
 FOR EACH ROW EXECUTE FUNCTION public.cj_message_travel_epoch_guard();

CREATE FUNCTION public.cj_message_travel_reference_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE receipt record; chat record; context record;
BEGIN
 SELECT * INTO receipt FROM public.cj_message_receipt WHERE scope=NEW.scope AND message_id=NEW.message_id;
 IF NOT FOUND OR (NEW.run_id,NEW.conversation_id,NEW.generation,NEW.sequence,NEW.input_sha256,NEW.reference_version)
    IS DISTINCT FROM (receipt.run_id,receipt.conversation_id,receipt.generation,receipt.sequence,receipt.input_sha256,receipt.travel_reference_version) THEN
   RAISE EXCEPTION 'original message reference mismatch';
 END IF;
 SELECT * INTO chat FROM public.cj_message_chat
 WHERE scope=NEW.scope AND conversation_id=NEW.conversation_id AND generation=NEW.generation;
 IF NOT FOUND OR NOT chat.active OR chat.last_sequence<>NEW.sequence THEN
   RAISE EXCEPTION 'accepted context reference has no matching current head';
 END IF;
 IF NEW.reference_kind='travel' THEN
   SELECT * INTO context FROM public.cj_travel_context WHERE scope=NEW.scope AND context_id=NEW.context_id;
   IF NOT FOUND OR NOT context.active OR context.version<>NEW.context_version THEN RAISE EXCEPTION 'travel context not current'; END IF;
 END IF;
 -- Exact raw MESSAGE-send.2 fields/hash are validated once by the repository codec;
 -- SQL does not reinterpret legacy raw JSON (including previously accepted escapes).
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER cj_message_travel_reference_consistent AFTER INSERT ON public.cj_message_travel_reference
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.cj_message_travel_reference_guard();
-- All functions are invoker-only. The ABI key is compatibility, never ownership/auth.
CREATE FUNCTION public.cj_message_travel_compatible(p_scope text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT p_scope=NULLIF(current_setting('cj.message_scope',true),'')
 AND (current_setting('cj.message_context_abi',true)='MESSAGE-TRAVEL-CONSUMER@1'
      OR NOT EXISTS(SELECT 1 FROM public.cj_message_context_profile p WHERE p.scope=p_scope))
$$;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_travel_context','cj_travel_context_action','cj_message_context_profile','cj_message_travel_reference'] LOOP
   EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
   EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',t);
   IF t='cj_message_context_profile' THEN
     EXECUTE format('CREATE POLICY cj_travel_owner ON public.%I FOR SELECT TO cj_m1_runtime USING(scope=NULLIF(current_setting(''cj.message_scope'',true),''''))',t);
   ELSE
     EXECUTE format('CREATE POLICY cj_travel_owner ON public.%I TO cj_m1_runtime USING(scope=NULLIF(current_setting(''cj.message_scope'',true),'''') AND current_setting(''cj.message_context_abi'',true)=''MESSAGE-TRAVEL-CONSUMER@1'') WITH CHECK(scope=NULLIF(current_setting(''cj.message_scope'',true),'''') AND current_setting(''cj.message_context_abi'',true)=''MESSAGE-TRAVEL-CONSUMER@1'')',t);
   END IF;
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft','cj_run_scope','cj_run_record','cj_run_event'] LOOP
   EXECUTE format('CREATE POLICY cj_travel_consumer ON public.%I AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_message_travel_compatible(scope)) WITH CHECK(public.cj_message_travel_compatible(scope))',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT ON public.cj_travel_context,public.cj_travel_context_action,
 public.cj_message_travel_reference TO cj_m1_runtime;
GRANT UPDATE(version,active,head_action_id) ON public.cj_travel_context TO cj_m1_runtime;
GRANT SELECT ON public.cj_message_context_profile TO cj_m1_runtime;
REVOKE ALL ON FUNCTION public.cj_travel_context_guard(),public.cj_travel_action_guard(),
 public.cj_message_context_activation_guard(),public.cj_message_travel_receipt_guard(),
 public.cj_message_travel_epoch_guard(),public.cj_message_travel_reference_guard(),
 public.cj_message_travel_compatible(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cj_message_travel_compatible(text) TO cj_m1_runtime;
-- No runtime DELETE/TRUNCATE, profile INSERT/UPDATE, role attribute or old-policy change.
