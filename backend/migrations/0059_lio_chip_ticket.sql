-- local runtime only: #1727 part 2, one-time tap-to-ask tickets for Lio answers and the daily
-- question-quota exemption they earn (the receipt keeps its question day; a flag marks it free) (JT 2026-11-25: 20 exempt questions per Beijing day, at most
-- 3 chips per answer of which one can be used free, three chained levels).
-- No SECURITY DEFINER, no new role, no DELETE grant. Account erasure: rows cascade from
-- cj_message_chat and cj_message_receipt, which the existing business/message hook deletes.
CREATE TABLE public.cj_lio_chip (
 scope text NOT NULL,
 conversation_id text NOT NULL,
 generation text NOT NULL,
 answer_message_id text NOT NULL,
 chip_index smallint NOT NULL CHECK(chip_index BETWEEN 0 AND 2),
 ticket text NOT NULL CHECK(ticket ~ '^[A-Za-z0-9_-]{43}$'),
 label_sha256 text NOT NULL CHECK(label_sha256 ~ '^[0-9a-f]{64}$'),
 -- Level of this chip in a chain of chip questions: the answer to a typed question offers level 1,
 -- the answer to a level-n chip question offers level n+1. Levels above 3 are never free.
 depth smallint NOT NULL CHECK(depth BETWEEN 1 AND 4),
 issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 -- The question the traveler sent with this ticket (every valid use, free or not): the next answer's level.
 used_message_id text,
 used_at timestamptz,
 -- The same question when it was also free of the daily count.
 redeemed_message_id text,
 redeemed_at timestamptz,
 redeemed_xid xid8,
 PRIMARY KEY(scope,answer_message_id,chip_index),
 UNIQUE(scope,ticket),
 UNIQUE(scope,used_message_id),
 UNIQUE(scope,redeemed_message_id),
 CHECK(expires_at>issued_at AND expires_at<=issued_at+interval '24 hours'),
 CHECK((used_message_id IS NULL)=(used_at IS NULL)),
 CHECK((redeemed_message_id IS NULL)=(redeemed_at IS NULL) AND (redeemed_at IS NULL)=(redeemed_xid IS NULL)),
 CHECK(redeemed_at IS NULL OR (used_at IS NOT NULL AND redeemed_message_id=used_message_id)),
 FOREIGN KEY(scope,conversation_id,generation)
  REFERENCES public.cj_message_chat(scope,conversation_id,generation) ON DELETE CASCADE,
 FOREIGN KEY(scope,answer_message_id) REFERENCES public.cj_message_receipt(scope,message_id) ON DELETE CASCADE
);
CREATE INDEX cj_lio_chip_redeemed_day ON public.cj_lio_chip(scope,redeemed_at) WHERE redeemed_at IS NOT NULL;
ALTER TABLE public.cj_lio_chip ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cj_lio_chip FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.cj_lio_chip FROM PUBLIC;
CREATE POLICY lio_chip_runtime ON public.cj_lio_chip TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON public.cj_lio_chip AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON public.cj_lio_chip TO cj_m1_runtime;
GRANT UPDATE(used_message_id,used_at,redeemed_message_id,redeemed_at,redeemed_xid) ON public.cj_lio_chip TO cj_m1_runtime;

-- A receipt is free of the daily count only through the flag below, set by the question trigger.
ALTER TABLE public.cj_message_receipt ADD COLUMN demo_chip_free boolean;
CREATE FUNCTION public.cj_demo_guard_chip_free() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF current_user='cj_m1_runtime' AND NEW.demo_chip_free IS DISTINCT FROM OLD.demo_chip_free THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='original demo receipt flag required';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_demo_guard_chip_free() FROM PUBLIC;
CREATE TRIGGER cj_demo_guard_chip_free BEFORE UPDATE OF demo_chip_free ON public.cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION public.cj_demo_guard_chip_free();

-- A ticket is used once, in the transaction that records the question, and only while every
-- rule holds. The same rules are checked by cj_lio_chip_redeem() (which answers false instead of
-- failing) and, as a backstop for any direct UPDATE, here.
CREATE FUNCTION public.cj_lio_chip_redeem_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF (NEW.scope,NEW.conversation_id,NEW.generation,NEW.answer_message_id,NEW.chip_index,NEW.ticket,
        NEW.label_sha256,NEW.depth,NEW.issued_at,NEW.expires_at)
       IS DISTINCT FROM (OLD.scope,OLD.conversation_id,OLD.generation,OLD.answer_message_id,OLD.chip_index,OLD.ticket,
        OLD.label_sha256,OLD.depth,OLD.issued_at,OLD.expires_at)
       OR OLD.used_at IS NOT NULL OR NEW.used_message_id IS NULL OR NEW.used_at IS NULL
       OR clock_timestamp()>=OLD.expires_at THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='chip ticket not usable';
    END IF;
    IF NEW.redeemed_at IS NOT NULL THEN
        IF NEW.redeemed_message_id IS DISTINCT FROM NEW.used_message_id OR NEW.redeemed_xid IS DISTINCT FROM pg_current_xact_id()
           OR OLD.depth>3
           OR EXISTS(SELECT 1 FROM public.cj_lio_chip s WHERE s.scope=OLD.scope AND s.answer_message_id=OLD.answer_message_id
                     AND s.redeemed_at IS NOT NULL)
           OR (SELECT count(*) FROM public.cj_lio_chip d WHERE d.scope=OLD.scope AND d.redeemed_at IS NOT NULL
               AND (d.redeemed_at AT TIME ZONE 'Asia/Shanghai')::date=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date)>=20 THEN
            RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='chip ticket not redeemable';
        END IF;
    ELSIF NEW.redeemed_message_id IS NOT NULL OR NEW.redeemed_xid IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='chip ticket not redeemable';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_chip_redeem_guard() FROM PUBLIC;
CREATE TRIGGER cj_lio_chip_redeem_guard BEFORE UPDATE ON public.cj_lio_chip
 FOR EACH ROW EXECUTE FUNCTION public.cj_lio_chip_redeem_guard();
-- A ticket is born unused: no INSERT can arrive already used or already free.
CREATE FUNCTION public.cj_lio_chip_born_unused() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NEW.used_message_id IS NOT NULL OR NEW.used_at IS NOT NULL OR NEW.redeemed_message_id IS NOT NULL
       OR NEW.redeemed_at IS NOT NULL OR NEW.redeemed_xid IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='chip ticket must be issued unused';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_chip_born_unused() FROM PUBLIC;
CREATE TRIGGER cj_lio_chip_born_unused BEFORE INSERT ON public.cj_lio_chip
 FOR EACH ROW EXECUTE FUNCTION public.cj_lio_chip_born_unused();
CREATE FUNCTION public.cj_lio_chip_reject_truncate() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF TG_OP='TRUNCATE' THEN
        RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='chip tickets are never truncated';
    END IF;
    RETURN OLD;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_chip_reject_truncate() FROM PUBLIC;
CREATE TRIGGER cj_lio_chip_no_truncate BEFORE TRUNCATE ON public.cj_lio_chip
 FOR EACH STATEMENT EXECUTE FUNCTION public.cj_lio_chip_reject_truncate();

-- Offer chips for one answer: the caller passes label hashes and fresh random tickets; the level
-- comes from the answer itself (a message paid for by a level-n chip offers level n+1). Returns the
-- number of rows written; an answer that already has chips is left as it is.
CREATE FUNCTION public.cj_lio_chip_issue(p_answer_message_id text, p_label_sha256 text[], p_tickets text[])
 RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    s text := nullif(current_setting('cj.message_scope',true),'');
    r public.cj_message_receipt%ROWTYPE;
    level smallint;
    written integer := 0;
    i integer;
    issued timestamptz := clock_timestamp();
BEGIN
    IF s IS NULL OR p_label_sha256 IS NULL OR p_tickets IS NULL
       OR coalesce(array_length(p_label_sha256,1),0) NOT BETWEEN 1 AND 3
       OR array_length(p_label_sha256,1)<>array_length(p_tickets,1) THEN
        RETURN 0;
    END IF;
    SELECT * INTO r FROM public.cj_message_receipt WHERE scope=s AND message_id=p_answer_message_id;
    IF NOT FOUND THEN RETURN 0; END IF;
    -- A question sent with any valid chip ticket (free or not) is one level deeper than the chip.
    SELECT least(depth+1,4) INTO level FROM public.cj_lio_chip WHERE scope=s AND used_message_id=p_answer_message_id;
    level := coalesce(level,1);
    FOR i IN 1..array_length(p_tickets,1) LOOP
        INSERT INTO public.cj_lio_chip(scope,conversation_id,generation,answer_message_id,chip_index,ticket,label_sha256,
                                       depth,issued_at,expires_at)
        VALUES(s,r.conversation_id,r.generation,p_answer_message_id,i-1,p_tickets[i],p_label_sha256[i],level,
               issued,issued+interval '24 hours')
        ON CONFLICT DO NOTHING;
        written := written+(CASE WHEN FOUND THEN 1 ELSE 0 END);
    END LOOP;
    RETURN written;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_chip_issue(text,text[],text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cj_lio_chip_issue(text,text[],text[]) TO cj_m1_runtime;

-- Use a ticket for the question being recorded in this transaction. The use is always recorded when
-- the ticket is valid for this text (it sets the level of the next answer's chips); the question is
-- also free of the daily count only when every rule holds. Never an error: any other case leaves an
-- ordinary question that counts. Returns whether the question is free.
CREATE FUNCTION public.cj_lio_chip_redeem(p_ticket text, p_label_sha256 text, p_message_id text)
 RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    s text := nullif(current_setting('cj.message_scope',true),'');
    r public.cj_lio_chip%ROWTYPE;
    free boolean;
BEGIN
    IF s IS NULL OR p_ticket IS NULL OR p_label_sha256 IS NULL OR p_message_id IS NULL THEN RETURN false; END IF;
    SELECT * INTO r FROM public.cj_lio_chip WHERE scope=s AND ticket=p_ticket FOR UPDATE;
    IF NOT FOUND OR r.used_at IS NOT NULL OR r.label_sha256<>p_label_sha256 OR clock_timestamp()>=r.expires_at THEN
        RETURN false;
    END IF;
    free := r.depth<=3
        AND NOT EXISTS(SELECT 1 FROM public.cj_lio_chip x WHERE x.scope=s AND x.answer_message_id=r.answer_message_id
                       AND x.redeemed_at IS NOT NULL)
        AND (SELECT count(*) FROM public.cj_lio_chip d WHERE d.scope=s AND d.redeemed_at IS NOT NULL
             AND (d.redeemed_at AT TIME ZONE 'Asia/Shanghai')::date=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date)<20;
    IF free THEN
        UPDATE public.cj_lio_chip SET used_message_id=p_message_id,used_at=clock_timestamp(),
               redeemed_message_id=p_message_id,redeemed_at=clock_timestamp(),redeemed_xid=pg_current_xact_id()
         WHERE scope=s AND answer_message_id=r.answer_message_id AND chip_index=r.chip_index;
    ELSE
        UPDATE public.cj_lio_chip SET used_message_id=p_message_id,used_at=clock_timestamp()
         WHERE scope=s AND answer_message_id=r.answer_message_id AND chip_index=r.chip_index;
    END IF;
    RETURN free;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.cj_lio_chip_redeem(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cj_lio_chip_redeem(text,text,text) TO cj_m1_runtime;

-- The daily question count (0052) skips exactly the receipt a ticket was made free for in this very
-- transaction (it keeps its question day, which readers use, and is flagged instead); the invitation
-- check still applies. Everything else is the 0052 function.
CREATE OR REPLACE FUNCTION public.cj_demo_accept_question() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    NEW.demo_question_day := NULL;
    NEW.demo_chip_free := NULL;
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
    IF EXISTS(SELECT 1 FROM public.cj_lio_chip c WHERE c.scope=NEW.scope AND c.redeemed_message_id=NEW.message_id
              AND c.redeemed_xid=pg_current_xact_id()) THEN
        NEW.demo_chip_free := true;
        RETURN NEW;
    END IF;
    IF (SELECT count(*) FROM public.cj_message_receipt
        WHERE scope=NEW.scope AND demo_question_day=NEW.demo_question_day AND demo_chip_free IS NOT TRUE) >= 400 THEN
        RAISE EXCEPTION USING ERRCODE='P5D01', MESSAGE='demo daily question limit';
    END IF;
    RETURN NEW;
END;
$$;
