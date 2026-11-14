-- local runtime only. Versioned Lio dialogue originals.
ALTER TABLE public.cj_message_receipt
    ADD COLUMN demo_dialogue_protocol text,
    ADD CONSTRAINT cj_demo_dialogue_planning_origin CHECK (
        demo_dialogue_protocol IS NULL
        OR (demo_dialogue_protocol='LIO-message.1'
            AND demo_dialogue_input_sha256 IS NOT NULL));

CREATE FUNCTION public.cj_demo_dialogue_protocol_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF NEW.demo_dialogue_protocol IS DISTINCT FROM OLD.demo_dialogue_protocol THEN
        RAISE EXCEPTION 'immutable dialogue protocol';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER cj_demo_dialogue_protocol_immutable
    BEFORE UPDATE OF demo_dialogue_protocol ON public.cj_message_receipt
    FOR EACH ROW EXECUTE FUNCTION public.cj_demo_dialogue_protocol_guard();
