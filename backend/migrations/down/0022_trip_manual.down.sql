-- local runtime only: refuse removal of any retained manual origin/confirmation.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM cj_trip_manual_basis)
       OR EXISTS (SELECT 1 FROM cj_trip_manual_intent) THEN
        RAISE EXCEPTION 'trip_manual down refused: retained original manual input';
    END IF;
END $$;
DROP TABLE cj_trip_manual_intent;
DROP TABLE cj_trip_manual_basis;
