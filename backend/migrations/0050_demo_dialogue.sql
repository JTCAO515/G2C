-- local runtime only. Existing MESSAGE receipts keep their original bytes and versions.
ALTER TABLE public.cj_message_receipt
    ADD COLUMN demo_dialogue_input_sha256 text,
    ADD COLUMN demo_dialogue_locale text,
    ADD CONSTRAINT cj_demo_dialogue_origin CHECK (
        (demo_dialogue_input_sha256 IS NULL AND demo_dialogue_locale IS NULL)
        OR (demo_dialogue_input_sha256 IS NOT NULL
            AND demo_dialogue_input_sha256 ~ '^[0-9a-f]{64}$'
            AND demo_dialogue_locale IS NOT NULL AND demo_dialogue_locale IN ('zh','en')
            AND travel_reference_version IS NOT DISTINCT FROM 1)
    );

CREATE FUNCTION public.cj_demo_dialogue_origin_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF (NEW.demo_dialogue_input_sha256,NEW.demo_dialogue_locale) IS DISTINCT FROM
        (OLD.demo_dialogue_input_sha256,OLD.demo_dialogue_locale) THEN
        RAISE EXCEPTION 'immutable dialogue origin';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER cj_demo_dialogue_origin_immutable
    BEFORE UPDATE OF demo_dialogue_input_sha256,demo_dialogue_locale ON public.cj_message_receipt
    FOR EACH ROW EXECUTE FUNCTION public.cj_demo_dialogue_origin_guard();
