-- local runtime only: retained source/action data may never be erased by down.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_trip_scoped_basis) OR EXISTS(SELECT 1 FROM cj_trip_scoped_action) THEN
  RAISE EXCEPTION 'trip_scoped_edit down refused: retained source/action';
 END IF;
END $$;
DROP TABLE cj_trip_scoped_action;
DROP TABLE cj_trip_scoped_basis;
