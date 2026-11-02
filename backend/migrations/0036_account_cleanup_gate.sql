-- local runtime only: durable original-operation task/accounting preflight.
-- App/device capabilities cannot bypass this gate or supply its reason.
CREATE TABLE cj_cleanup_account_gate (
 subject_digest text NOT NULL,
 operation_id text PRIMARY KEY REFERENCES cj_cleanup_request(operation_id),
 reason text CHECK(reason IN ('original_tasks_not_yet_stopped','original_usage_outcome_unresolved'))
);
ALTER TABLE cj_cleanup_account_gate ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_cleanup_account_gate FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_cleanup_account_gate TO cj_local_cleanup
 USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''))
 WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_cleanup_account_gate TO cj_local_cleanup;
GRANT UPDATE(reason) ON cj_cleanup_account_gate TO cj_local_cleanup;
CREATE TRIGGER cleanup_gate_progress AFTER INSERT OR UPDATE ON cj_cleanup_account_gate
 FOR EACH ROW EXECUTE FUNCTION cj_cleanup_progress_revision();
