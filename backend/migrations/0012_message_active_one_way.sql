-- ADR-0008: a closed conversation must never grant a fresh send position again.
CREATE FUNCTION cj_message_guard_active() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.active = false AND NEW.active = true THEN
    RAISE EXCEPTION 'closed conversation cannot be reactivated';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER cj_message_active_one_way BEFORE UPDATE OF active ON cj_message_chat
FOR EACH ROW EXECUTE FUNCTION cj_message_guard_active();
