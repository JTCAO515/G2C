-- local runtime only: #1770 service conversation kind and server-initiated assistant messages
-- (ADR-0009 sections 3 and 4). No SECURITY DEFINER, no new role, no new DELETE grant.
-- Account erasure: both new tables cascade from cj_message_chat, which the existing
-- business/message hook already deletes; the authority row also cascades from its
-- SERVICE-REQUEST history row (0056 retention/account erasure). Runtime gets no UPDATE/DELETE.
ALTER TABLE cj_message_chat ADD COLUMN conversation_kind text NOT NULL DEFAULT 'trip'
 CHECK(conversation_kind IN ('trip','service'));
CREATE UNIQUE INDEX cj_message_chat_one_service ON cj_message_chat(scope)
 WHERE conversation_kind='service' AND active;
CREATE FUNCTION cj_message_chat_kind_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.conversation_kind IS DISTINCT FROM OLD.conversation_kind THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='conversation kind is fixed';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_message_chat_kind_fixed() FROM PUBLIC;
CREATE TRIGGER message_chat_kind_fixed BEFORE UPDATE ON cj_message_chat
 FOR EACH ROW EXECUTE FUNCTION cj_message_chat_kind_fixed();

-- Server-initiated assistant message: takes the next number of the same conversation head.
CREATE TABLE cj_service_message (
 scope text NOT NULL,
 conversation_id text NOT NULL,
 generation text NOT NULL,
 sequence bigint NOT NULL CHECK(sequence>0),
 message_id text NOT NULL CHECK(message_id ~ '^sm_[0-9a-f]{32}$'),
 origin text NOT NULL CHECK(origin='server_initiated'),
 provided_by_human boolean NOT NULL,
 body_zh text NOT NULL CHECK(char_length(body_zh) BETWEEN 1 AND 2000),
 body_en text NOT NULL CHECK(char_length(body_en) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,conversation_id,generation,sequence),
 UNIQUE(scope,message_id),
 FOREIGN KEY(scope,conversation_id,generation)
  REFERENCES cj_message_chat(scope,conversation_id,generation) ON DELETE CASCADE
);
-- Internal audit: which service request and which state change authorized the message.
-- The primary key is the idempotency key: one state change, one message. Runtime: INSERT only.
CREATE TABLE cj_service_message_authority (
 scope text NOT NULL,
 request_id text NOT NULL,
 history_seq integer NOT NULL CHECK(history_seq>=1),
 to_state text NOT NULL,
 message_id text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,request_id,history_seq),
 UNIQUE(scope,message_id),
 FOREIGN KEY(scope,message_id) REFERENCES cj_service_message(scope,message_id)
  ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(scope,request_id,history_seq) REFERENCES cj_service_request_history(scope,request_id,seq)
  ON DELETE CASCADE
);
ALTER TABLE cj_service_message ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_message FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_service_message_authority ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_message_authority FORCE ROW LEVEL SECURITY;
REVOKE ALL ON cj_service_message,cj_service_message_authority FROM PUBLIC;
CREATE POLICY service_message_runtime ON cj_service_message TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON cj_service_message AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON cj_service_message TO cj_m1_runtime;
CREATE POLICY service_message_authority_runtime ON cj_service_message_authority FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
CREATE POLICY account_retired ON cj_service_message_authority AS RESTRICTIVE FOR INSERT TO cj_m1_runtime
 WITH CHECK(public.cj_account_scope_current(scope));
GRANT INSERT ON cj_service_message_authority TO cj_m1_runtime;

-- One total order per conversation head (ADR-0008): a server message must take exactly
-- last_sequence+1 of an active service conversation and never a number a receipt holds.
CREATE FUNCTION cj_service_message_head() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_message_chat c WHERE c.scope=NEW.scope AND c.conversation_id=NEW.conversation_id
  AND c.generation=NEW.generation AND c.active AND c.conversation_kind='service'
  AND c.last_sequence+1=NEW.sequence;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service message outside head'; END IF;
 PERFORM 1 FROM cj_message_receipt r WHERE r.scope=NEW.scope AND r.conversation_id=NEW.conversation_id
  AND r.generation=NEW.generation AND r.sequence=NEW.sequence;
 IF FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service message sequence taken'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_message_head() FROM PUBLIC;
CREATE TRIGGER service_message_head BEFORE INSERT ON cj_service_message
 FOR EACH ROW EXECUTE FUNCTION cj_service_message_head();
CREATE FUNCTION cj_message_receipt_not_service_sequence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_service_message m WHERE m.scope=NEW.scope AND m.conversation_id=NEW.conversation_id
  AND m.generation=NEW.generation AND m.sequence=NEW.sequence;
 IF FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='receipt sequence taken'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_message_receipt_not_service_sequence() FROM PUBLIC;
CREATE TRIGGER message_receipt_not_service_sequence BEFORE INSERT ON cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION cj_message_receipt_not_service_sequence();
CREATE FUNCTION cj_service_message_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service message is append-only'; END $$;
REVOKE ALL ON FUNCTION cj_service_message_append_only() FROM PUBLIC;
CREATE TRIGGER service_message_append_only BEFORE UPDATE ON cj_service_message
 FOR EACH ROW EXECUTE FUNCTION cj_service_message_append_only();
CREATE TRIGGER service_message_append_only BEFORE UPDATE ON cj_service_message_authority
 FOR EACH ROW EXECUTE FUNCTION cj_service_message_append_only();

-- Isolation (ADR-0009 section 4): a service conversation never feeds a RUN (no planning
-- context, no memory extraction) and never carries travel/trip/edit references or NEEDS.
CREATE FUNCTION cj_message_not_service() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE row_scope text; row_message text;
BEGIN
 row_scope:=to_jsonb(NEW)->>TG_ARGV[0];
 row_message:=to_jsonb(NEW)->>'message_id';
 PERFORM 1 FROM cj_message_receipt r JOIN cj_message_chat c
  ON (c.scope,c.conversation_id,c.generation)=(r.scope,r.conversation_id,r.generation)
  WHERE r.scope=row_scope AND r.message_id=row_message AND c.conversation_kind='service';
 IF FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service conversation is isolated'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_message_not_service() FROM PUBLIC;
CREATE TRIGGER message_not_service BEFORE INSERT ON cj_message_delivery
 FOR EACH ROW EXECUTE FUNCTION cj_message_not_service('scope');
CREATE TRIGGER message_not_service BEFORE INSERT ON cj_message_travel_reference
 FOR EACH ROW EXECUTE FUNCTION cj_message_not_service('scope');
CREATE TRIGGER message_not_service BEFORE INSERT ON cj_message_trip_reference
 FOR EACH ROW EXECUTE FUNCTION cj_message_not_service('scope');
CREATE TRIGGER message_not_service BEFORE INSERT ON cj_message_edit_reference
 FOR EACH ROW EXECUTE FUNCTION cj_message_not_service('scope');
CREATE TRIGGER message_not_service BEFORE INSERT ON cj_message_needs_binding
 FOR EACH ROW EXECUTE FUNCTION cj_message_not_service('message_scope');
CREATE FUNCTION cj_service_message_reject_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'service message truncate refused'; END $$;
REVOKE ALL ON FUNCTION cj_service_message_reject_truncate() FROM PUBLIC;
CREATE TRIGGER service_message_no_truncate BEFORE TRUNCATE ON cj_service_message
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_message_reject_truncate();
CREATE TRIGGER service_message_no_truncate BEFORE TRUNCATE ON cj_service_message_authority
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_message_reject_truncate();

-- Cleanup: SELECT only, for the verify-only business/service-sessions hook of the original
-- approved account operation. Rows are removed by the chat cascade, never by this role.
CREATE POLICY service_message_cleanup_verify ON cj_service_message FOR SELECT TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
GRANT SELECT(scope) ON cj_service_message TO cj_local_cleanup;
CREATE POLICY service_message_cleanup_verify ON cj_service_message_authority FOR SELECT TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
GRANT SELECT(scope) ON cj_service_message_authority TO cj_local_cleanup;
