-- local runtime only: #1970 (W4-3b), the account's own record of consent to Lio memory suggestions.
-- Append-only: every grant or withdrawal is a new row, the current state is the last row, and no
-- row means "not consented". The runtime role can SELECT and INSERT only (no UPDATE, no DELETE);
-- rows cascade away with the account's message scope (the existing business/message hook).
-- No SECURITY DEFINER, no new role.
CREATE TABLE public.cj_lio_memory_consent (
 scope text NOT NULL,
 seq integer NOT NULL CHECK(seq>=1),
 state text NOT NULL CHECK(state IN ('granted','withdrawn')),
 -- Version of the consent text the App showed; the text itself is never stored.
 consent_text_version text NOT NULL CHECK(consent_text_version ~ '^[A-Za-z0-9._:-]{1,64}$'),
 request_id text NOT NULL CHECK(request_id ~ '^[A-Za-z0-9._:-]{1,128}$'),
 changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,seq),
 UNIQUE(scope,request_id),
 FOREIGN KEY(scope) REFERENCES public.cj_message_scope(scope) ON DELETE CASCADE
);
ALTER TABLE public.cj_lio_memory_consent ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_lio_memory_consent FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.cj_lio_memory_consent FROM PUBLIC;
CREATE POLICY lio_memory_consent_runtime ON public.cj_lio_memory_consent TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON public.cj_lio_memory_consent AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON public.cj_lio_memory_consent TO cj_m1_runtime;

-- One total order per account: each row is the next number and flips the state of the row before it
-- (a repeated state is a no-op the caller does not write). Concurrent writers serialise on the scope row.
CREATE FUNCTION public.cj_lio_memory_consent_order() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    last_seq integer;
    last_state text;
BEGIN
    PERFORM 1 FROM public.cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
    SELECT seq,state INTO last_seq,last_state FROM public.cj_lio_memory_consent
     WHERE scope=NEW.scope ORDER BY seq DESC LIMIT 1;
    IF NEW.seq IS DISTINCT FROM coalesce(last_seq,0)+1 OR NEW.state IS NOT DISTINCT FROM last_state THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='consent record out of order';
    END IF;
    NEW.changed_at := clock_timestamp();
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_memory_consent_order() FROM PUBLIC;
CREATE TRIGGER cj_lio_memory_consent_order BEFORE INSERT ON public.cj_lio_memory_consent
 FOR EACH ROW EXECUTE FUNCTION public.cj_lio_memory_consent_order();
CREATE FUNCTION public.cj_lio_memory_consent_reject_truncate() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='consent records are never truncated';
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_memory_consent_reject_truncate() FROM PUBLIC;
CREATE TRIGGER cj_lio_memory_consent_no_truncate BEFORE TRUNCATE ON public.cj_lio_memory_consent
 FOR EACH STATEMENT EXECUTE FUNCTION public.cj_lio_memory_consent_reject_truncate();
