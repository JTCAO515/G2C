-- local runtime only: never discard an original account reconciliation gate.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_cleanup_account_gate) THEN
  RAISE EXCEPTION 'account cleanup gate contains original operation evidence';
 END IF;
END $$;
DROP TABLE cj_cleanup_account_gate;
