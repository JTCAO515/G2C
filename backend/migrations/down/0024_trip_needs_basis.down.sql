-- local runtime only: retain all original source/confirmation lineage.
DO $$
BEGIN
 IF EXISTS(SELECT 1 FROM cj_trip_needs_basis) THEN
  RAISE EXCEPTION 'trip_needs_basis down refused: retained original source';
 END IF;
END $$;
DROP TABLE cj_trip_needs_basis;
