-- local runtime only: use the original MESSAGE scope privileges; no new grants.
ALTER TABLE public.cj_message_scope
 ADD COLUMN demo_invite_digest text,
 ADD COLUMN demo_invite_expires_at timestamptz,
 ADD COLUMN demo_session_floor bigint,
 ADD COLUMN demo_revoked_at timestamptz,
 ADD CONSTRAINT cj_demo_invitation_shape CHECK (
    (demo_invite_digest IS NULL AND demo_invite_expires_at IS NULL AND demo_session_floor IS NULL
     AND demo_revoked_at IS NULL)
    OR (
      scope ~ '^local:https://local[.]g2c[.]invalid:m4-synthetic-demo-[a-z0-9]{12}$'
      AND demo_invite_digest IS NOT NULL AND demo_invite_digest ~ '^[a-f0-9]{64}$'
      AND demo_invite_expires_at IS NOT NULL AND demo_invite_expires_at <= '2027-01-01T00:00:00+08:00'::timestamptz
      AND demo_session_floor IS NOT NULL AND demo_session_floor>=0
    )
 );

CREATE FUNCTION public.cj_demo_guard_invitation() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF current_user='cj_m1_runtime' THEN
        IF TG_OP='INSERT' THEN
            IF NEW.demo_invite_digest IS NOT NULL THEN
                RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='operator invitation required';
            END IF;
        ELSIF ROW(NEW.demo_invite_digest,NEW.demo_invite_expires_at,NEW.demo_session_floor,NEW.demo_revoked_at)
            IS DISTINCT FROM ROW(OLD.demo_invite_digest,OLD.demo_invite_expires_at,OLD.demo_session_floor,OLD.demo_revoked_at) THEN
            RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='operator invitation required';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_demo_guard_invitation() FROM PUBLIC;
CREATE TRIGGER cj_demo_guard_invitation BEFORE INSERT OR UPDATE ON public.cj_message_scope
 FOR EACH ROW EXECUTE FUNCTION public.cj_demo_guard_invitation();

ALTER TABLE public.cj_message_receipt ADD COLUMN demo_question_day date;
CREATE INDEX cj_demo_receipt_day ON public.cj_message_receipt(scope,demo_question_day)
 WHERE demo_question_day IS NOT NULL;

CREATE FUNCTION public.cj_demo_accept_question() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    NEW.demo_question_day := NULL;
    IF NEW.scope !~ '^local:https://local[.]g2c[.]invalid:m4-synthetic-demo-' THEN
        RETURN NEW;
    END IF;
    -- An actual row version serializes receipt admission even at stricter isolation.
    UPDATE public.cj_message_scope
      SET scope=scope
      WHERE scope=NEW.scope AND demo_invite_expires_at>clock_timestamp() AND demo_revoked_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='P5D02', MESSAGE='demo invitation inactive';
    END IF;
    NEW.demo_question_day := (clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
    IF (SELECT count(*) FROM public.cj_message_receipt
        WHERE scope=NEW.scope AND demo_question_day=NEW.demo_question_day) >= 40 THEN
        RAISE EXCEPTION USING ERRCODE='P5D01', MESSAGE='demo daily question limit';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_demo_accept_question() FROM PUBLIC;
CREATE TRIGGER cj_demo_accept_question BEFORE INSERT ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_demo_accept_question();

CREATE FUNCTION public.cj_demo_guard_question_day() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF current_user='cj_m1_runtime' AND NEW.demo_question_day IS DISTINCT FROM OLD.demo_question_day THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='original demo receipt day required';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_demo_guard_question_day() FROM PUBLIC;
CREATE TRIGGER cj_demo_guard_question_day BEFORE UPDATE OF demo_question_day ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_demo_guard_question_day();
