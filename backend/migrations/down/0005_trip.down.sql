-- Reverts 0005 (backend/trip/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_trip_receipt;
DROP TABLE cj_trip_record;
DROP TABLE cj_trip_proposal;
DROP TABLE cj_trip_scope;
