-- Reverts 0001: drops the migration ledger schema. Only after every later migration is reverted.
DROP SCHEMA cj CASCADE;
