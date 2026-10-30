-- local runtime only: #227 explicit typed context, no reinterpretation of legacy IDs.
ALTER TABLE cj_memory_item
 ADD COLUMN context_kind text NOT NULL DEFAULT 'legacy',
 ADD COLUMN travel_context_id text GENERATED ALWAYS AS
   (CASE WHEN context_kind='travel' THEN context_id ELSE NULL END) STORED;
ALTER TABLE cj_memory_item
 ADD CONSTRAINT cj_memory_context_kind_check CHECK
   (context_kind IN ('legacy','travel') AND (context_kind='legacy' OR extent='current')),
 ADD CONSTRAINT cj_memory_owned_travel_context_fk FOREIGN KEY(scope,travel_context_id)
   REFERENCES cj_travel_context(scope,context_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX cj_memory_active_typed_slot
 ON cj_memory_item(scope,subject,slot,extent,context_kind,context_id) WHERE status='active';
DROP INDEX cj_memory_active_slot;
