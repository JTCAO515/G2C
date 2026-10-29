-- Additive local registered-exit metadata. Existing M1 rows/policies are unchanged.
CREATE TABLE cj_local_metered_profile (
 scope text PRIMARY KEY REFERENCES cj_local_run_protection(scope) ON DELETE RESTRICT,
 version text NOT NULL CHECK(version='registered-exit.1')
);
CREATE TABLE cj_message_metered_requirement (
 scope text NOT NULL REFERENCES cj_local_metered_profile(scope) ON DELETE RESTRICT,
 message_id text NOT NULL, run_id text NOT NULL,
 version text NOT NULL CHECK(version='registered-exit.1'),
 PRIMARY KEY(scope,message_id), UNIQUE(scope,run_id),
 FOREIGN KEY(scope,message_id,run_id) REFERENCES cj_message_receipt(scope,message_id,run_id) ON DELETE CASCADE
);
CREATE TABLE cj_run_metered_binding (
 scope text NOT NULL REFERENCES cj_local_metered_profile(scope) ON DELETE RESTRICT,
 run_id text NOT NULL,
 ledger_scope text NOT NULL REFERENCES cj_usage_ledger_candidate(scope_id) ON DELETE RESTRICT,
 unit text NOT NULL CHECK(unit='provider_call'),
 period_start bigint NOT NULL CHECK(period_start>=0),
 period_end bigint NOT NULL CHECK(period_end>period_start),
 source_abi text NOT NULL CHECK(source_abi='RUN-USAGE-OPERATIONS@1'),
 PRIMARY KEY(scope,run_id), UNIQUE(scope,run_id,ledger_scope),
 FOREIGN KEY(scope,run_id) REFERENCES cj_run_record(scope,run_id) ON DELETE CASCADE,
 CHECK(ledger_scope='u'||encode(sha256(convert_to(
  '['||to_json(scope)::text||',"provider_call",'||period_start::text||','||period_end::text||']','UTF8')),'hex'))
);
CREATE TABLE cj_run_metered_operation (
 scope text NOT NULL, run_id text NOT NULL,
 operation_key text NOT NULL CHECK(length(operation_key) BETWEEN 1 AND 200),
 ledger_scope text NOT NULL,
 registration_id text NOT NULL CHECK(length(registration_id) BETWEEN 1 AND 200),
 kind text NOT NULL CHECK(kind IN ('model','tool','memory')),
 attempt_id text NOT NULL CHECK(length(attempt_id) BETWEEN 1 AND 200),
 operation_id text NOT NULL CHECK(length(operation_id) BETWEEN 1 AND 200),
 command_bytes bytea NOT NULL, input_bytes bytea NOT NULL,
 PRIMARY KEY(scope,run_id,operation_key),
 UNIQUE(scope,attempt_id), UNIQUE(scope,operation_id),
 FOREIGN KEY(scope,run_id,ledger_scope) REFERENCES cj_run_metered_binding(scope,run_id,ledger_scope) ON DELETE CASCADE
);

ALTER TABLE cj_local_metered_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_local_metered_profile FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_message_metered_requirement ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_message_metered_requirement FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_run_metered_binding ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_run_metered_binding FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_run_metered_operation ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_run_metered_operation FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_profile_read ON cj_local_metered_profile FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY cj_m2_requirement_read ON cj_message_metered_requirement FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY cj_m2_requirement_insert ON cj_message_metered_requirement FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY cj_m2_binding_read ON cj_run_metered_binding FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY cj_m2_binding_insert ON cj_run_metered_binding FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY cj_m2_operation_read ON cj_run_metered_operation FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY cj_m2_operation_insert ON cj_run_metered_operation FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
GRANT SELECT ON cj_local_metered_profile TO cj_m1_runtime;
GRANT SELECT,INSERT ON cj_message_metered_requirement,cj_run_metered_binding,cj_run_metered_operation TO cj_m1_runtime;

-- One activation boundary for every initializer; operator code need not repeat
-- the idle-work checks. Never take a RUN write lock while holding MESSAGE.
CREATE FUNCTION cj_registered_profile_activation() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 PERFORM scope FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'original message scope unavailable' USING ERRCODE='23514';
 END IF;
 IF EXISTS(SELECT 1 FROM public.cj_local_metered_profile WHERE scope=NEW.scope) THEN
  RETURN NEW;
 END IF;
 IF EXISTS(SELECT 1 FROM public.cj_message_delivery WHERE scope=NEW.scope AND NOT acknowledged)
    OR EXISTS(SELECT 1 FROM public.cj_run_record WHERE scope=NEW.scope AND status IN ('queued','running')) THEN
  RAISE EXCEPTION 'original pending work prevents registered activation' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cj_registered_profile_activation BEFORE INSERT ON cj_local_metered_profile
 FOR EACH ROW EXECUTE FUNCTION cj_registered_profile_activation();

-- Deferred checks run before commit while transaction-LOCAL authority still lives.
-- Fully qualified tables prevent search_path or temporary-object substitution.
CREATE FUNCTION cj_registered_receipt_requirement() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_local_metered_profile WHERE scope=NEW.scope) THEN
  IF NOT EXISTS(SELECT 1 FROM public.cj_message_metered_requirement
                WHERE scope=NEW.scope AND message_id=NEW.message_id AND run_id=NEW.run_id)
     OR EXISTS(SELECT 1 FROM public.cj_local_run_requirement
               WHERE scope=NEW.scope AND message_id=NEW.message_id) THEN
   RAISE EXCEPTION 'registered execution requirement unavailable' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION cj_registered_requirement_consistency() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.cj_local_metered_profile WHERE scope=NEW.scope)
    OR EXISTS(SELECT 1 FROM public.cj_local_run_requirement
              WHERE scope=NEW.scope AND message_id=NEW.message_id) THEN
  RAISE EXCEPTION 'registered execution requirement mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION cj_legacy_requirement_not_upgraded() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_local_metered_profile WHERE scope=NEW.scope) THEN
  RAISE EXCEPTION 'legacy execution requirement unavailable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER cj_registered_receipt_requirement
 AFTER INSERT ON cj_message_receipt DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION cj_registered_receipt_requirement();
CREATE CONSTRAINT TRIGGER cj_registered_requirement_consistency
 AFTER INSERT ON cj_message_metered_requirement DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION cj_registered_requirement_consistency();
CREATE CONSTRAINT TRIGGER cj_legacy_requirement_not_upgraded
 AFTER INSERT ON cj_local_run_requirement DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION cj_legacy_requirement_not_upgraded();
