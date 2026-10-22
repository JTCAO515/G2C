# CJ017 author verification

Environment: local Python 3.14, synthetic in-memory Trip/Proposal fixtures only.
Fixed base: `8deb696f8149b4f5aa70c767be6c3a263b036227`.
Input domain: CJ015 `5fd115fc97e542bc8776a445d8245fd272000e56`, unchanged at base.

PASS: 15 unittest cases, [raw output](unit-tests.txt), exercising actual CJ015 DTOs
and Proposal validation, NFC/NFD exact differences, original immutable bytes/version,
selected-only title/text/order, unselected and protected absolute positions,
duplicate/foreign/missing IDs, invalid/canonical/unsupported shape, no inherited or
transferred evidence, immutable outputs, all required host metadata, sticky conflict
and unknown observations without text loss, and unconditional save unavailability.

Reproduction command is in the module README. No additional dependency or lock edits.
Independent Review/Testing: UNRUN (Main routes fixed candidate). CI/integration:
UNRUN. PostgreSQL/provider/network/auth/physical device: UNRUN. Issue22 complete
editor/save/receipt/persistent fixed-state/CJ035 feasibility/I acceptance: UNRUN.
No public release or formal API publication, and no claim of complete fixed protection
when trusted protection context or reality constraints are unknown.
