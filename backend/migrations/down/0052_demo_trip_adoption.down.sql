DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_demo_trip_adoption) THEN
        RAISE EXCEPTION 'demo Trip adoption originals must be preserved';
    END IF;
END $$;
DROP TABLE public.cj_demo_trip_adoption;
