-- local runtime only: append actual Lio4 outer origin, preserving the Lio3/core binding.
ALTER TABLE public.cj_message_receipt DROP CONSTRAINT cj_lio_wire_origin_shape;
ALTER TABLE public.cj_message_receipt ADD CONSTRAINT cj_lio_wire_origin_shape CHECK (
    (lio_wire_protocol IS NULL AND lio_wire_input IS NULL)
    OR (lio_wire_protocol IS NOT NULL AND lio_wire_protocol IN ('LIO-message.3','LIO-message.4')
        AND lio_wire_input IS NOT NULL AND octet_length(lio_wire_input) BETWEEN 1 AND 16384
        AND demo_dialogue_protocol IS NOT NULL AND demo_dialogue_protocol='LIO-message.1'
        AND demo_dialogue_input_sha256 IS NOT NULL
        AND encode(sha256(lio_wire_input),'hex')=demo_dialogue_input_sha256));

CREATE OR REPLACE FUNCTION public.cj_lio_wire_origin_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE wire jsonb; core jsonb;
BEGIN
    IF TG_OP='UPDATE' AND (NEW.lio_wire_protocol,NEW.lio_wire_input) IS DISTINCT FROM
        (OLD.lio_wire_protocol,OLD.lio_wire_input) THEN
        RAISE EXCEPTION 'immutable Lio wire origin';
    END IF;
    IF NEW.lio_wire_protocol IS NOT NULL THEN
        wire:=convert_from(NEW.lio_wire_input,'UTF8')::jsonb;
        core:=convert_from(NEW.raw_input,'UTF8')::jsonb;
        IF wire->>'version' IS DISTINCT FROM NEW.lio_wire_protocol
            OR wire->>'message_id' IS DISTINCT FROM NEW.message_id
            OR wire->>'text' IS DISTINCT FROM core->>'text'
            OR wire->>'locale' IS DISTINCT FROM NEW.demo_dialogue_locale
            OR (wire ? 'conversation_id' AND wire->>'conversation_id' IS DISTINCT FROM NEW.conversation_id)
        THEN RAISE EXCEPTION 'Lio wire differs from original receipt'; END IF;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.cj_lio_wire_origin_guard() FROM PUBLIC;
