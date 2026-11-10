DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_message_receipt WHERE demo_dialogue_protocol IS NOT NULL) THEN
        RAISE EXCEPTION 'Lio dialogue originals must be preserved';
    END IF;
END $$;

DROP TRIGGER cj_demo_dialogue_protocol_immutable ON public.cj_message_receipt;
DROP FUNCTION public.cj_demo_dialogue_protocol_guard();
ALTER TABLE public.cj_message_receipt DROP COLUMN demo_dialogue_protocol;
