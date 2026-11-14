DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_message_receipt WHERE demo_dialogue_input_sha256 IS NOT NULL) THEN
        RAISE EXCEPTION 'demo dialogue originals must be preserved';
    END IF;
END $$;
DROP TRIGGER cj_demo_dialogue_origin_immutable ON public.cj_message_receipt;
DROP FUNCTION public.cj_demo_dialogue_origin_guard();
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_demo_dialogue_origin,
    DROP COLUMN demo_dialogue_locale,
    DROP COLUMN demo_dialogue_input_sha256;
