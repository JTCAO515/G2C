-- local runtime only: approved #26 dedicated-role payload redaction, not fees/chat.
CREATE TABLE cj_run_payload_erasure (
 owner_digest text NOT NULL CHECK(owner_digest~'^[0-9a-f]{64}$'),
 kind text NOT NULL CHECK(kind IN ('run','input','job','reference')),
 object_digest text NOT NULL CHECK(object_digest~'^[0-9a-f]{64}$'),
 payload_sha256 text CHECK(payload_sha256~'^[0-9a-f]{64}$'),
 c_enqueue_sha256 text CHECK(c_enqueue_sha256~'^[0-9a-f]{64}$'),
 outcome text NOT NULL CHECK(outcome IN ('stopped','empty','erased')),
 PRIMARY KEY(owner_digest,kind,object_digest),
 CHECK((kind='job')=(c_enqueue_sha256 IS NOT NULL)),
 CHECK((kind='run')=(outcome='stopped')),
 CHECK(outcome<>'erased' OR payload_sha256 IS NOT NULL)
);
ALTER TABLE cj_run_payload_erasure ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_run_payload_erasure FORCE ROW LEVEL SECURITY;

CREATE FUNCTION cj_payload_key(kind text,parts text[]) RETURNS text
 LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER AS $$
DECLARE raw bytea:=convert_to('CJ-PAYLOAD-ERASURE@1','UTF8')||decode('00','hex')||convert_to(kind,'UTF8'); part text;
BEGIN
 FOREACH part IN ARRAY parts LOOP raw:=raw||decode('00','hex')||convert_to(part,'UTF8'); END LOOP;
 RETURN encode(sha256(raw),'hex');
END $$;
CREATE FUNCTION cj_payload_barrier_key(scope text) RETURNS bigint
 LANGUAGE sql IMMUTABLE STRICT SECURITY INVOKER
 RETURN pg_catalog.hashtextextended('CJ-MEMORY-PAYLOAD-BARRIER@1:'||scope,0);

-- Read-only original root-plan observation, before physical hook dispatch.
CREATE FUNCTION cj_payload_plan(scope_arg text) RETURNS boolean
 LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT EXISTS(SELECT 1 FROM public.cj_cleanup_operation o
  WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
   AND o.purpose='memory' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/message'->>'domain_scope'=scope_arg
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'checkpoints/run'->>'domain_scope'=scope_arg
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/usage'->>'domain_scope'=scope_arg
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/message'->'selection'->>'kind'='memory'
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/message'->'selection'=
       convert_from(o.plan_bytes,'UTF8')::jsonb->'checkpoints/run'->'selection'
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/message'->'selection'=
       convert_from(o.plan_bytes,'UTF8')::jsonb->'business/usage'->'selection')
$$;
CREATE FUNCTION cj_payload_write(scope_arg text,target_arg text) RETURNS boolean
 LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT current_user='cj_local_cleanup' AND public.cj_payload_plan(scope_arg)
  AND current_setting('cj.cleanup_purpose',true)='memory'
  AND current_setting('cj.cleanup_target',true)=target_arg
  AND EXISTS(SELECT 1 FROM public.cj_cleanup_step s
   WHERE s.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
    AND s.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
    AND s.target=target_arg AND s.state='in_progress'
    AND s.invocation_id=nullif(current_setting('cj.cleanup_invocation',true),''))
$$;
CREATE POLICY payload_runtime_read ON cj_run_payload_erasure FOR SELECT TO cj_m1_runtime
 USING(owner_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex')
       AND public.cj_account_scope_current(nullif(current_setting('cj.message_scope',true),'')));
CREATE POLICY payload_cleanup_read ON cj_run_payload_erasure FOR SELECT TO cj_local_cleanup
 USING(owner_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex')
       AND public.cj_payload_plan(nullif(current_setting('cj.cleanup_scope',true),'')));
CREATE POLICY payload_cleanup_insert ON cj_run_payload_erasure FOR INSERT TO cj_local_cleanup
 WITH CHECK(owner_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex')
   AND ((kind IN ('run','reference') AND public.cj_payload_write(nullif(current_setting('cj.cleanup_scope',true),''),'business/message'))
    OR (kind IN ('run','input','job') AND public.cj_payload_write(nullif(current_setting('cj.cleanup_scope',true),''),'checkpoints/run'))));
GRANT SELECT ON cj_run_payload_erasure TO cj_m1_runtime;
GRANT SELECT,INSERT ON cj_run_payload_erasure TO cj_local_cleanup;

CREATE FUNCTION cj_payload_run_current(scope_arg text,run_arg text) RETURNS boolean
 LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT NOT EXISTS(SELECT 1 FROM public.cj_run_payload_erasure p
  WHERE p.owner_digest=encode(sha256(convert_to(scope_arg,'UTF8')),'hex') AND p.kind='run'
   AND p.object_digest=public.cj_payload_key('run',ARRAY[run_arg]))
$$;
CREATE FUNCTION cj_payload_input_erased(scope_arg text,table_arg text,run_arg text,key_arg text,command_arg bytea) RETURNS boolean
 LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT EXISTS(SELECT 1 FROM public.cj_run_payload_erasure p
  WHERE p.owner_digest=encode(sha256(convert_to(scope_arg,'UTF8')),'hex') AND p.kind='input'
   AND p.object_digest=public.cj_payload_key('input',ARRAY[table_arg,run_arg,key_arg])
   AND p.outcome='erased' AND p.payload_sha256=convert_from(command_arg,'UTF8')::jsonb->>'input_digest')
$$;
CREATE FUNCTION cj_payload_job_current(scope_arg text,jid text,attempt text) RETURNS boolean
 LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT NOT EXISTS(SELECT 1 FROM public.cj_run_payload_erasure p
  WHERE p.owner_digest=encode(sha256(convert_to(scope_arg,'UTF8')),'hex') AND p.kind='job'
   AND p.object_digest=public.cj_payload_key('job',ARRAY[jid,attempt]))
$$;

-- Historical reads stay available. New/late writes to stopped originals do not.
CREATE POLICY payload_run_insert ON cj_run_record AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_payload_run_current(scope,run_id));
CREATE POLICY payload_run_update ON cj_run_record AS RESTRICTIVE FOR UPDATE TO cj_m1_runtime
 USING(true) WITH CHECK(public.cj_payload_run_current(scope,run_id));
CREATE POLICY payload_event_insert ON cj_run_event AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_payload_run_current(scope,run_id));
CREATE POLICY payload_step_insert ON cj_run_step_usage AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_payload_run_current(scope,run_id));
CREATE POLICY payload_operation_insert ON cj_run_metered_operation AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_payload_run_current(scope,run_id));
CREATE POLICY payload_job_insert ON cj_run_background_job AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_payload_job_current(scope,job_id,attempt_id));
CREATE POLICY payload_job_update ON cj_run_background_job AS RESTRICTIVE FOR UPDATE TO cj_m1_runtime
 USING(true) WITH CHECK(public.cj_payload_job_current(scope,job_id,attempt_id));

ALTER TABLE cj_run_step_usage ALTER COLUMN input_bytes DROP NOT NULL,
 ADD CONSTRAINT payload_step_erased CHECK(input_bytes IS NOT NULL OR
   public.cj_payload_input_erased(scope,'cj_run_step_usage',run_id,step_key,command_bytes));
ALTER TABLE cj_run_metered_operation ALTER COLUMN input_bytes DROP NOT NULL,
 ADD CONSTRAINT payload_operation_erased CHECK(input_bytes IS NOT NULL OR
   public.cj_payload_input_erased(scope,'cj_run_metered_operation',run_id,operation_key,command_bytes));
ALTER TABLE cj_run_record DROP CONSTRAINT cj_run_record_check,
 ADD CONSTRAINT payload_run_erased CHECK(
  (usage_command_bytes IS NULL AND usage_input_bytes IS NULL) OR
  (usage_command_bytes IS NOT NULL AND (usage_input_bytes IS NOT NULL OR
    public.cj_payload_input_erased(scope,'cj_run_record',run_id,'original',usage_command_bytes))));

CREATE OR REPLACE FUNCTION cj_run_guard_original_binding() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF (NEW.scope,NEW.run_id,NEW.conversation_id,NEW.generation,NEW.message_id,NEW.message_sequence,NEW.usage_command_bytes)
  IS DISTINCT FROM (OLD.scope,OLD.run_id,OLD.conversation_id,OLD.generation,OLD.message_id,OLD.message_sequence,OLD.usage_command_bytes)
 THEN RAISE EXCEPTION 'immutable original run association'; END IF;
 IF NEW.usage_input_bytes IS DISTINCT FROM OLD.usage_input_bytes THEN
  IF current_user<>'cj_local_cleanup' OR NEW.usage_input_bytes IS NOT NULL THEN
   RAISE EXCEPTION 'immutable original run association';
  END IF;
  IF NOT public.cj_payload_write(OLD.scope,'checkpoints/run') OR
     NOT public.cj_payload_input_erased(OLD.scope,'cj_run_record',OLD.run_id,'original',OLD.usage_command_bytes)
  THEN RAISE EXCEPTION 'immutable original run association'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION cj_payload_input_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.input_bytes IS NULL THEN RAISE EXCEPTION 'new original input required'; END IF;
  RETURN NEW;
 END IF;
 IF current_user NOT IN ('cj_m1_runtime','cj_local_cleanup') THEN RETURN NEW; END IF;
 IF to_jsonb(NEW)-'input_bytes' IS DISTINCT FROM to_jsonb(OLD)-'input_bytes'
 THEN RAISE EXCEPTION 'immutable original operation header'; END IF;
 IF NEW.input_bytes IS DISTINCT FROM OLD.input_bytes THEN
  IF current_user<>'cj_local_cleanup' OR NEW.input_bytes IS NOT NULL THEN
   RAISE EXCEPTION 'immutable original operation header';
  END IF;
  IF NOT public.cj_payload_write(OLD.scope,'checkpoints/run') THEN
   RAISE EXCEPTION 'immutable original operation header';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER payload_step_original BEFORE INSERT OR UPDATE ON cj_run_step_usage FOR EACH ROW EXECUTE FUNCTION cj_payload_input_guard();
CREATE TRIGGER payload_operation_original BEFORE INSERT OR UPDATE ON cj_run_metered_operation FOR EACH ROW EXECUTE FUNCTION cj_payload_input_guard();
CREATE FUNCTION cj_payload_reference_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF current_user IN ('cj_m1_runtime','cj_local_cleanup') AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) AND NOT
  (NEW.source_content IS NULL AND NEW.content_sha256 IS NULL AND public.cj_payload_write(OLD.scope,'business/message')
   AND to_jsonb(NEW)-'source_content'-'content_sha256'=to_jsonb(OLD)-'source_content'-'content_sha256')
 THEN RAISE EXCEPTION 'original source cache cannot be restored or rebound'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER payload_trip_reference BEFORE UPDATE ON cj_message_trip_reference FOR EACH ROW EXECUTE FUNCTION cj_payload_reference_guard();
CREATE TRIGGER payload_edit_reference BEFORE UPDATE ON cj_message_edit_reference FOR EACH ROW EXECUTE FUNCTION cj_payload_reference_guard();

CREATE FUNCTION cj_payload_write_barrier() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE selected_scope text;
BEGIN
 IF TG_OP='DELETE' THEN selected_scope:=OLD.scope; ELSE selected_scope:=NEW.scope; END IF;
 IF current_user<>'cj_local_cleanup' OR current_setting('cj.cleanup_purpose',true) IS DISTINCT FROM 'memory' THEN
  PERFORM pg_advisory_xact_lock_shared(public.cj_payload_barrier_key(selected_scope));
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_message_chat','cj_message_receipt','cj_message_delivery',
  'cj_run_record','cj_run_event','cj_run_step_usage','cj_run_metered_operation',
  'cj_run_background_job','cj_message_trip_reference','cj_message_edit_reference'] LOOP
  EXECUTE format('CREATE TRIGGER payload_write_barrier BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION cj_payload_write_barrier()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_message_receipt','cj_message_chat','cj_message_delivery','cj_message_trip_reference',
  'cj_message_edit_reference','cj_run_record','cj_run_event','cj_run_step_usage','cj_run_metered_operation',
  'cj_run_metered_binding','cj_run_background_job'] LOOP
  EXECUTE format('CREATE POLICY payload_memory_read ON %I FOR SELECT TO cj_local_cleanup USING(public.cj_payload_plan(scope))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_run_record','cj_run_step_usage','cj_run_metered_operation','cj_run_background_job'] LOOP
  EXECUTE format('CREATE POLICY payload_memory_update ON %I FOR UPDATE TO cj_local_cleanup USING(public.cj_payload_write(scope,''checkpoints/run'')) WITH CHECK(public.cj_payload_write(scope,''checkpoints/run''))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_message_trip_reference','cj_message_edit_reference','cj_message_delivery'] LOOP
  EXECUTE format('CREATE POLICY payload_memory_update ON %I FOR UPDATE TO cj_local_cleanup USING(public.cj_payload_write(scope,''business/message'')) WITH CHECK(public.cj_payload_write(scope,''business/message''))',t);
 END LOOP;
END $$;
GRANT UPDATE(input_bytes) ON cj_run_step_usage,cj_run_metered_operation,cj_run_background_job TO cj_local_cleanup;
GRANT UPDATE(usage_input_bytes) ON cj_run_record TO cj_local_cleanup;
GRANT UPDATE(source_content,content_sha256) ON cj_message_trip_reference,cj_message_edit_reference TO cj_local_cleanup;
GRANT UPDATE(acknowledged) ON cj_message_delivery TO cj_local_cleanup;
REVOKE ALL ON FUNCTION cj_payload_key(text,text[]),cj_payload_barrier_key(text),cj_payload_plan(text),
 cj_payload_write(text,text),cj_payload_run_current(text,text),cj_payload_input_erased(text,text,text,text,bytea),
 cj_payload_job_current(text,text,text),cj_payload_input_guard(),cj_payload_reference_guard(),
 cj_payload_write_barrier() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_payload_key(text,text[]),cj_payload_barrier_key(text),
 cj_payload_run_current(text,text),cj_payload_input_erased(text,text,text,text,bytea),cj_payload_job_current(text,text,text)
 TO cj_m1_runtime,cj_local_cleanup;
GRANT EXECUTE ON FUNCTION cj_payload_plan(text),cj_payload_write(text,text) TO cj_local_cleanup;
