LOCK TABLE cj_local_metered_profile,cj_message_metered_requirement,
 cj_run_metered_binding,cj_run_metered_operation IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_local_metered_profile)
    OR EXISTS(SELECT 1 FROM cj_message_metered_requirement)
    OR EXISTS(SELECT 1 FROM cj_run_metered_binding)
    OR EXISTS(SELECT 1 FROM cj_run_metered_operation) THEN
  RAISE EXCEPTION 'registered execution records exist; downgrade refused';
 END IF;
END $$;
DROP TRIGGER cj_registered_receipt_requirement ON cj_message_receipt;
DROP TRIGGER cj_legacy_requirement_not_upgraded ON cj_local_run_requirement;
DROP TRIGGER cj_registered_requirement_consistency ON cj_message_metered_requirement;
DROP FUNCTION cj_registered_receipt_requirement();
DROP FUNCTION cj_registered_requirement_consistency();
DROP FUNCTION cj_legacy_requirement_not_upgraded();
DROP TRIGGER cj_registered_profile_activation ON cj_local_metered_profile;
DROP FUNCTION cj_registered_profile_activation();
DROP TABLE cj_run_metered_operation;
DROP TABLE cj_run_metered_binding;
DROP TABLE cj_message_metered_requirement;
DROP TABLE cj_local_metered_profile;
