LOCK TABLE cj_message_needs_selection,cj_message_needs_binding,cj_run_step_usage,cj_usage_ledger_candidate,cj_run_event IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_message_needs_selection)
 OR EXISTS(SELECT 1 FROM cj_message_needs_binding)
 OR EXISTS(SELECT 1 FROM cj_run_step_usage)
 OR EXISTS(SELECT 1 FROM cj_run_event WHERE kind='budget_denied' OR (kind='draft_outcome' AND value='budget_exhausted'))
 THEN RAISE EXCEPTION 'local context/attempt/admission data exists; no destructive downgrade'; END IF;
END $$;
ALTER TABLE cj_run_event DROP CONSTRAINT cj_run_event_kind_check, DROP CONSTRAINT cj_run_event_check,
 ADD CONSTRAINT cj_run_event_kind_check CHECK(kind IN ('started','text_delta','effect_committed','completed','failed','cancelled','context_invalid','unknown','draft_outcome')),
 ADD CONSTRAINT cj_run_event_check CHECK(
 (kind IN ('text_delta','effect_committed') AND length(value)>0)
 OR (kind='draft_outcome' AND value IN ('validation_failed','provider_failed','provider_unknown'))
 OR (kind NOT IN ('text_delta','effect_committed','draft_outcome') AND value=''));
DROP TRIGGER cj_needs_no_truncate ON cj_needs_revision;
DROP TRIGGER cj_needs_no_truncate ON cj_needs_record;
DROP TRIGGER cj_needs_no_truncate ON cj_needs_scope;
DROP FUNCTION cj_needs_reject_truncate();
DROP TRIGGER cj_needs_write_fence ON cj_needs_revision;
DROP TRIGGER cj_needs_write_fence ON cj_needs_record;
DROP TRIGGER cj_needs_write_fence ON cj_needs_scope;
DROP FUNCTION cj_needs_write_fence();
DROP FUNCTION cj_needs_fence_key(text);
REVOKE SELECT, UPDATE(ledger,revision) ON cj_usage_ledger_candidate FROM cj_m1_runtime;
DROP POLICY cj_m1_usage_read ON cj_usage_ledger_candidate;
DROP POLICY cj_m1_usage_update ON cj_usage_ledger_candidate;
REVOKE SELECT ON cj_needs_scope,cj_needs_record,cj_needs_revision FROM cj_m1_runtime;
DROP POLICY cj_m1_needs_read ON cj_needs_scope;
DROP POLICY cj_m1_needs_read ON cj_needs_record;
DROP POLICY cj_m1_needs_read ON cj_needs_revision;
ALTER TABLE cj_needs_scope NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_scope DISABLE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_record NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_record DISABLE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_revision NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_revision DISABLE ROW LEVEL SECURITY;
DROP TABLE cj_run_step_usage;
DROP TABLE cj_message_needs_binding;
DROP TABLE cj_message_needs_selection;
