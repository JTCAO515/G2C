-- local runtime only. Original explicit dialogue adoption intent.
CREATE TABLE public.cj_demo_trip_adoption (
    scope text NOT NULL,
    action_id text NOT NULL CHECK (octet_length(action_id) BETWEEN 1 AND 256),
    original_message_id text NOT NULL,
    proposal_id text NOT NULL,
    candidate_hash text NOT NULL CHECK (candidate_hash ~ '^[0-9a-f]{64}$'),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(scope,action_id),
    FOREIGN KEY(scope,original_message_id)
        REFERENCES public.cj_message_receipt(scope,message_id) ON DELETE CASCADE
);
CREATE INDEX cj_demo_trip_adoption_origin ON public.cj_demo_trip_adoption(scope,original_message_id);
ALTER TABLE public.cj_demo_trip_adoption ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_demo_trip_adoption FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_demo_trip_adoption_owner ON public.cj_demo_trip_adoption TO cj_m1_runtime
    USING(scope=nullif(current_setting('cj.message_scope',true),''))
    WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON public.cj_demo_trip_adoption AS RESTRICTIVE TO cj_m1_runtime
    USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON public.cj_demo_trip_adoption TO cj_m1_runtime;
