DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_demo_needs_card) THEN
        RAISE EXCEPTION 'demo needs card originals must be preserved';
    END IF;
END $$;
DROP TABLE public.cj_demo_needs_card;
