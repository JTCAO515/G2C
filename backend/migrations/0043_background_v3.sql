-- local runtime only: preserve BG2 originals and explicit BG3 immutable headers.
ALTER TABLE cj_run_background_job
 ADD COLUMN protocol text NOT NULL DEFAULT 'RUN-BACKGROUND@2'
   CHECK(protocol IN ('RUN-BACKGROUND@2','RUN-BACKGROUND@3')),
 ADD COLUMN decision_source_sha256 text CHECK(decision_source_sha256~'^[0-9a-f]{64}$'),
 ADD CONSTRAINT cj_background_decision_header CHECK(
   (protocol='RUN-BACKGROUND@2' AND decision_source_sha256 IS NULL) OR
   (protocol='RUN-BACKGROUND@3' AND decision_source_sha256 IS NOT NULL));
GRANT INSERT(protocol,decision_source_sha256) ON cj_run_background_job TO cj_m1_runtime;

-- Old BG2 binaries set no selector and continue to observe only their own v2.
-- This label separates compatibility, not authority: all original scope/account
-- policies and the real C phase holders remain mandatory.
CREATE POLICY background_protocol ON cj_run_background_job AS RESTRICTIVE TO cj_m1_runtime
 USING(protocol=COALESCE(NULLIF(current_setting('cj.background_protocol',true),''),'RUN-BACKGROUND@2'))
 WITH CHECK(protocol=COALESCE(NULLIF(current_setting('cj.background_protocol',true),''),'RUN-BACKGROUND@2'));

CREATE FUNCTION cj_background_header_immutable() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF ROW(NEW.protocol,NEW.decision_source_sha256) IS DISTINCT FROM ROW(OLD.protocol,OLD.decision_source_sha256) THEN
  RAISE EXCEPTION 'immutable original background protocol/decision header';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_background_header_immutable() FROM PUBLIC;
CREATE TRIGGER background_header_immutable BEFORE UPDATE ON cj_run_background_job
 FOR EACH ROW EXECUTE FUNCTION cj_background_header_immutable();
