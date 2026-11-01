-- local runtime only: refuse to erase retained result and recovery sources.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_trip_scoped_result) THEN
  RAISE EXCEPTION 'trip_scoped_result down refused: retained result';
 END IF;
END $$;
DROP TABLE cj_trip_scoped_result;
