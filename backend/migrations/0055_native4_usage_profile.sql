-- local runtime only: explicit operator qualification, no account refill/automatic upgrade.
ALTER TABLE public.cj_usage_ledger_candidate DROP CONSTRAINT cj_usage_ledger_candidate_format_version_check;
ALTER TABLE public.cj_usage_ledger_candidate ADD CONSTRAINT cj_usage_ledger_candidate_format_version_check
 CHECK(format_version IN (1,2));

CREATE TABLE public.cj_native4_usage_profile (
 scope text NOT NULL REFERENCES public.cj_message_scope(scope) ON DELETE CASCADE,
 ledger_scope text NOT NULL REFERENCES public.cj_usage_ledger_candidate(scope_id) ON DELETE CASCADE,
 policy text NOT NULL CHECK(policy='lio-native4.1'),
 PRIMARY KEY(scope,ledger_scope)
);
ALTER TABLE public.cj_native4_usage_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_native4_usage_profile FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.cj_native4_usage_profile FROM PUBLIC;
CREATE POLICY cj_native4_usage_read ON public.cj_native4_usage_profile FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),'')
   AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY account_retired ON public.cj_native4_usage_profile AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope));
GRANT SELECT ON public.cj_native4_usage_profile TO cj_m1_runtime;
-- The runtime cannot INSERT/UPDATE/DELETE qualification or change ledger format_version.
-- B explicitly upgrades the same original account, preserving Config and every attempt.
-- Eligibility metadata follows either approved account-parent cleanup; no new DELETE grant.
