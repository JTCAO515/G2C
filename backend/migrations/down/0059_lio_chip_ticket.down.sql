-- local runtime only: refuse to drop chip tickets while any exist (they hold redemption history that
-- the daily exemption count reads); restore the 0052 question-quota function and drop the free flag.
LOCK TABLE public.cj_lio_chip IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.cj_lio_chip) THEN
  RAISE EXCEPTION 'lio_chip_ticket down refused: retained private data';
 END IF;
END $$;
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
DROP TRIGGER cj_demo_guard_chip_free ON public.cj_message_receipt;
DROP FUNCTION public.cj_demo_guard_chip_free();
ALTER TABLE public.cj_message_receipt DROP COLUMN demo_chip_free;
DROP FUNCTION public.cj_lio_chip_redeem(text,text,text);
DROP FUNCTION public.cj_lio_chip_issue(text,text[],text[]);
DROP TABLE public.cj_lio_chip;
DROP FUNCTION public.cj_lio_chip_reject_truncate();
DROP FUNCTION public.cj_lio_chip_redeem_guard();
