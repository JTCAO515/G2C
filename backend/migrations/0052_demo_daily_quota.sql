-- local runtime only. Preserve the existing owner lock, invite checks and original counts.
CREATE TABLE public.cj_demo_quota_upgrade (
    singleton boolean PRIMARY KEY CHECK (singleton)
);
ALTER TABLE public.cj_demo_quota_upgrade ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_demo_quota_upgrade FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.cj_demo_quota_upgrade FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.cj_demo_accept_question() RETURNS trigger
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
        WHERE scope=NEW.scope AND demo_question_day=NEW.demo_question_day) >= 400 THEN
        RAISE EXCEPTION USING ERRCODE='P5D01', MESSAGE='demo daily question limit';
    END IF;
    RETURN NEW;
END;
$$;
