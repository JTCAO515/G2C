-- CJ019 candidate only. CJ005 owns registration/application; no grants/RLS.
-- Only receipts are new: authoritative scope/source/item remain CJ011 tables.
CREATE TABLE cj_memory_management_action (
 scope text NOT NULL REFERENCES cj_memory_scope,
 action_id text NOT NULL,
 operation text NOT NULL CHECK(operation IN ('pause','resume')),
 original_input bytea NOT NULL,
 item_id text COLLATE "C" NOT NULL,
 version bigint NOT NULL CHECK(version>1),
 status text NOT NULL CHECK(status IN ('active','disabled')),
 PRIMARY KEY(scope,action_id),
 UNIQUE(scope,item_id,version),
 FOREIGN KEY(scope,item_id) REFERENCES cj_memory_item,
 CHECK((operation='pause' AND status='disabled') OR (operation='resume' AND status='active'))
);
