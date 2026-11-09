-- local runtime only: use the original MESSAGE scope privileges; no new grants.
ALTER TABLE public.cj_message_scope
 ADD COLUMN demo_invite_digest text,
 ADD COLUMN demo_invite_expires_at timestamptz,
 ADD COLUMN demo_session_floor bigint,
 ADD COLUMN demo_revoked_at timestamptz,
 ADD COLUMN demo_question_day date,
 ADD COLUMN demo_question_count smallint NOT NULL DEFAULT 0,
 ADD CONSTRAINT cj_demo_invitation_shape CHECK (
    (demo_invite_digest IS NULL AND demo_invite_expires_at IS NULL AND demo_session_floor IS NULL
     AND demo_revoked_at IS NULL AND demo_question_day IS NULL AND demo_question_count=0)
    OR (
      scope ~ '^local:https://local[.]g2c[.]invalid:m4-synthetic-demo-[a-z0-9]{12}$'
      AND demo_invite_digest IS NOT NULL AND demo_invite_digest ~ '^[a-f0-9]{64}$'
      AND demo_invite_expires_at IS NOT NULL AND demo_invite_expires_at <= '2027-01-01T00:00:00+08:00'::timestamptz
      AND demo_session_floor IS NOT NULL AND demo_session_floor>=0
      AND ((demo_question_day IS NULL AND demo_question_count=0)
           OR (demo_question_day IS NOT NULL AND demo_question_count BETWEEN 1 AND 40))
    )
 );

CREATE FUNCTION public.cj_demo_accept_question() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    accepted_at timestamptz := clock_timestamp();
    accepted_day date := (accepted_at AT TIME ZONE 'Asia/Shanghai')::date;
BEGIN
    IF NEW.scope !~ '^local:https://local[.]g2c[.]invalid:m4-synthetic-demo-' THEN
        RETURN NEW;
    END IF;
    UPDATE public.cj_message_scope
      SET demo_question_day=accepted_day,
          demo_question_count=CASE WHEN demo_question_day=accepted_day THEN demo_question_count+1 ELSE 1 END
      WHERE scope=NEW.scope AND demo_invite_expires_at>accepted_at AND demo_revoked_at IS NULL
        AND (demo_question_day IS DISTINCT FROM accepted_day OR demo_question_count<40);
    IF FOUND THEN RETURN NEW; END IF;
    IF EXISTS(SELECT 1 FROM public.cj_message_scope WHERE scope=NEW.scope
               AND demo_invite_expires_at>accepted_at AND demo_revoked_at IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='P5D01', MESSAGE='demo daily question limit';
    END IF;
    RAISE EXCEPTION USING ERRCODE='P5D02', MESSAGE='demo invitation inactive';
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_demo_accept_question() FROM PUBLIC;
CREATE TRIGGER cj_demo_accept_question BEFORE INSERT ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_demo_accept_question();
