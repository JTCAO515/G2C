-- Internal local protection metadata; no public wire or existing table policy changes.
-- Upgrade with host processes stopped. Never classify unreadable old work as legacy.
LOCK TABLE cj_message_scope, cj_message_receipt, cj_message_delivery,
 cj_message_needs_selection, cj_message_needs_binding, cj_run_step_usage,
 cj_usage_ledger_candidate IN ACCESS EXCLUSIVE MODE;

CREATE TABLE cj_local_run_protection (
 scope text PRIMARY KEY REFERENCES cj_message_scope(scope),
 version text NOT NULL CHECK(version='local-budget-needs.1')
);
CREATE TABLE cj_local_run_requirement (
 scope text NOT NULL REFERENCES cj_local_run_protection(scope),
 message_id text NOT NULL, run_id text NOT NULL,
 version text NOT NULL CHECK(version='local-budget-needs.1'),
 PRIMARY KEY(scope,message_id), UNIQUE(scope,run_id),
 FOREIGN KEY(scope,message_id,run_id) REFERENCES cj_message_receipt(scope,message_id,run_id)
);

-- This transient matcher uses the exact Python ledger_scope_for byte encoding:
-- compact JSON [scope,"provider_call",integer,integer], UTF-8, SHA256.
-- Full attempt/receipt integrity stays with the existing USAGE codec; migration
-- never rewrites the ledger. Mapping corruption or unknown format aborts upgrade.
DO $$
DECLARE account record; original_scope text; matches bigint; start_at bigint; end_at bigint;
BEGIN
 FOR account IN SELECT scope_id,format_version,ledger FROM cj_usage_ledger_candidate LOOP
  IF account.format_version<>1 OR jsonb_typeof(account.ledger) IS DISTINCT FROM 'object'
     OR jsonb_typeof(account.ledger->'config') IS DISTINCT FROM 'object'
     OR jsonb_typeof(account.ledger->'config'->'unit') IS DISTINCT FROM 'string'
     OR length(account.ledger->'config'->>'unit') NOT BETWEEN 1 AND 200 THEN
   RAISE EXCEPTION 'unknown ledger mapping format; original operator reconciliation required';
  END IF;
  IF account.ledger->'config'->>'unit' <> 'provider_call' THEN CONTINUE; END IF;
  IF jsonb_typeof(account.ledger->'config'->'period_start') IS DISTINCT FROM 'number'
     OR jsonb_typeof(account.ledger->'config'->'period_end') IS DISTINCT FROM 'number'
     OR (account.ledger->'config'->>'period_start') !~ '^(0|[1-9][0-9]*)$'
     OR (account.ledger->'config'->>'period_end') !~ '^(0|[1-9][0-9]*)$' THEN
   RAISE EXCEPTION 'invalid original quota period; upgrade refused';
  END IF;
  start_at := (account.ledger->'config'->>'period_start')::bigint;
  end_at := (account.ledger->'config'->>'period_end')::bigint;
  IF end_at<=start_at THEN RAISE EXCEPTION 'invalid original quota period; upgrade refused'; END IF;
  SELECT count(*),min(scope) INTO matches,original_scope FROM cj_message_scope
   WHERE account.scope_id='u'||encode(sha256(convert_to(
    '['||to_json(scope)::text||',"provider_call",'||start_at::text||','||end_at::text||']','UTF8')),'hex');
  IF matches<>1 THEN RAISE EXCEPTION 'original quota owner unresolved; upgrade refused'; END IF;
  INSERT INTO cj_local_run_protection VALUES(original_scope,'local-budget-needs.1') ON CONFLICT DO NOTHING;
 END LOOP;
END $$;

INSERT INTO cj_local_run_protection(scope,version)
 SELECT protected.scope,'local-budget-needs.1' FROM (
  SELECT message_scope AS scope FROM cj_message_needs_selection
  UNION SELECT message_scope FROM cj_message_needs_binding
  UNION SELECT scope FROM cj_run_step_usage
 ) protected ON CONFLICT DO NOTHING;
-- The FK rejects unresolved scope references instead of silently skipping them.
INSERT INTO cj_local_run_requirement(scope,message_id,run_id,version)
 SELECT r.scope,r.message_id,r.run_id,'local-budget-needs.1'
 FROM cj_message_receipt r JOIN cj_local_run_protection p ON p.scope=r.scope;

ALTER TABLE cj_local_run_protection ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_local_run_protection FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_local_run_requirement ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_local_run_requirement FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m1_protection_read ON cj_local_run_protection FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY cj_m1_requirement_read ON cj_local_run_requirement FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY cj_m1_requirement_insert ON cj_local_run_requirement FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT ON cj_local_run_protection TO cj_m1_runtime;
GRANT SELECT,INSERT ON cj_local_run_requirement TO cj_m1_runtime;
