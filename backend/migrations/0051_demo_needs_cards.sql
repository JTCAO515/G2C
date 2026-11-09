-- local runtime only. Dialogue needs previews and explicit action receipts.
CREATE TABLE public.cj_demo_needs_card (
    scope text NOT NULL,
    origin_message_id text NOT NULL,
    origin_run_id text NOT NULL,
    card_id text NOT NULL CHECK (card_id ~ '^needs-[0-9a-f]{32}$'),
    version bigint NOT NULL CHECK (version BETWEEN 1 AND 64),
    fields bytea NOT NULL CHECK (octet_length(fields) BETWEEN 2 AND 131072),
    city text CHECK (city IS NULL OR octet_length(city) BETWEEN 1 AND 256),
    action_id text CHECK (action_id IS NULL OR octet_length(action_id) BETWEEN 1 AND 256),
    input_sha256 text CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    operation text CHECK (operation IN ('correct_needs','confirm_needs')),
    result_message_id text,
    PRIMARY KEY(scope,card_id,version),
    UNIQUE(scope,action_id),
    UNIQUE(scope,origin_run_id,version),
    FOREIGN KEY(scope,origin_message_id)
        REFERENCES public.cj_message_receipt(scope,message_id) ON DELETE CASCADE,
    FOREIGN KEY(scope,result_message_id)
        REFERENCES public.cj_message_receipt(scope,message_id) ON DELETE CASCADE,
    CHECK ((version=1 AND action_id IS NULL AND input_sha256 IS NULL
            AND operation IS NULL AND result_message_id IS NULL)
        OR (version>1 AND action_id IS NOT NULL AND input_sha256 IS NOT NULL
            AND operation IS NOT NULL
            AND ((operation='confirm_needs')=(result_message_id IS NOT NULL))))
);
CREATE INDEX cj_demo_needs_card_origin
    ON public.cj_demo_needs_card(scope,origin_message_id,version);
ALTER TABLE public.cj_demo_needs_card ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_demo_needs_card FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_demo_needs_card_owner ON public.cj_demo_needs_card TO cj_m1_runtime
    USING(scope=nullif(current_setting('cj.message_scope',true),''))
    WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON public.cj_demo_needs_card AS RESTRICTIVE TO cj_m1_runtime
    USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON public.cj_demo_needs_card TO cj_m1_runtime;
