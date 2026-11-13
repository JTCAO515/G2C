DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.cj_message_receipt WHERE lio_wire_protocol IS NOT NULL) THEN
        RAISE EXCEPTION 'Lio wire originals must be preserved';
    END IF;
END $$;
DROP TRIGGER cj_lio_wire_origin_immutable ON public.cj_message_receipt;
DROP FUNCTION public.cj_lio_wire_origin_guard();
ALTER TABLE public.cj_message_receipt DROP COLUMN lio_wire_input, DROP COLUMN lio_wire_protocol;
