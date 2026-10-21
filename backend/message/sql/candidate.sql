-- UNAPPLIED candidate, NOT a shared migration. No grants, roles or RLS policy assumed.
-- AUTH scope provisioning and database privilege policy must be reviewed before use.
CREATE TABLE cj_message_scope (scope text PRIMARY KEY);
CREATE TABLE cj_message_chat (
  scope text NOT NULL REFERENCES cj_message_scope(scope),
  conversation_id text NOT NULL,
  generation text NOT NULL,
  epoch bigint NOT NULL CHECK (epoch >= 0),
  last_sequence bigint NOT NULL DEFAULT 0 CHECK (last_sequence >= 0),
  active boolean NOT NULL DEFAULT true,
  PRIMARY KEY (scope, conversation_id),
  UNIQUE (scope, conversation_id, generation)
);
CREATE TABLE cj_message_receipt (
  scope text NOT NULL,
  message_id text NOT NULL,
  conversation_id text NOT NULL,
  generation text NOT NULL,
  sequence bigint NOT NULL CHECK (sequence > 0),
  run_id text NOT NULL,
  input_sha256 text NOT NULL CHECK (length(input_sha256) = 64),
  raw_input bytea NOT NULL,
  PRIMARY KEY (scope, message_id),
  UNIQUE (scope, conversation_id, generation, sequence),
  UNIQUE (scope, run_id),
  UNIQUE (scope, message_id, run_id),
  FOREIGN KEY (scope, conversation_id, generation)
    REFERENCES cj_message_chat(scope, conversation_id, generation)
);
CREATE TABLE cj_message_delivery (
  scope text NOT NULL,
  message_id text NOT NULL,
  run_id text NOT NULL,
  acknowledged boolean NOT NULL DEFAULT false,
  PRIMARY KEY (scope, run_id),
  FOREIGN KEY (scope, message_id, run_id)
    REFERENCES cj_message_receipt(scope, message_id, run_id)
);
CREATE INDEX cj_message_pending ON cj_message_delivery (scope, message_id) WHERE NOT acknowledged;
-- No physical-delete, TTL, provisioning, grant or acknowledgement API in this slice.
-- Cleanup must serialize on scope and preserve/reconcile original-action recovery.
