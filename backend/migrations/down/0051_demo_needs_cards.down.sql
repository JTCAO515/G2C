DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_demo_needs_card)
        OR EXISTS (SELECT 1 FROM public.cj_message_receipt WHERE demo_dialogue_protocol IS NOT NULL) THEN
        RAISE EXCEPTION 'demo needs card originals must be preserved';
    END IF;
END $$;
DROP TABLE public.cj_demo_needs_card;
DROP TRIGGER cj_demo_dialogue_protocol_immutable ON public.cj_message_receipt;
DROP FUNCTION public.cj_demo_dialogue_protocol_guard();
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_demo_dialogue_planning_origin,
    DROP COLUMN demo_dialogue_protocol;
