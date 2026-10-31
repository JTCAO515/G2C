-- local runtime only: no retained explicit action/context may be erased.
DO $$
BEGIN
 IF EXISTS(SELECT 1 FROM cj_trip_needs_action) OR EXISTS(SELECT 1 FROM cj_trip_needs_current) OR EXISTS(SELECT 1 FROM cj_trip_needs_edit) OR EXISTS(SELECT 1 FROM cj_trip_needs_plan_context) THEN
  RAISE EXCEPTION 'trip_needs_actions down refused: retained actions/context';
 END IF;
END $$;
DROP TABLE cj_trip_needs_plan_context;
DROP TABLE cj_trip_needs_edit;
DROP TABLE cj_trip_needs_current;
DROP TABLE cj_trip_needs_action;
