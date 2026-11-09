DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_message_scope WHERE demo_invite_digest IS NOT NULL) THEN
        RAISE EXCEPTION 'demo invitation state must be preserved';
    END IF;
END $$;
DROP TRIGGER cj_demo_accept_question ON public.cj_message_receipt;
DROP FUNCTION public.cj_demo_accept_question();
ALTER TABLE public.cj_message_scope
 DROP CONSTRAINT cj_demo_invitation_shape,
 DROP COLUMN demo_invite_digest,
 DROP COLUMN demo_invite_expires_at,
 DROP COLUMN demo_session_floor,
 DROP COLUMN demo_revoked_at,
 DROP COLUMN demo_question_day,
 DROP COLUMN demo_question_count;
