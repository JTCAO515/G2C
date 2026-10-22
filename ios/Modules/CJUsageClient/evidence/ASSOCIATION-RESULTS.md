# Author results — official original usage source

- PASS `association-tests-4.txt`: 10 test functions / 30 Swift Testing expanded cases.
  Nested scenarios additionally exercise both stages across actor, selection ABA,
  recovery and session invalidation; body/cancel tests cover both cancelled and
  noncancelled old reads after an actual body iterator await.
  Actual canonical MessageHTTPClient.query + generated MessageReceipt/recovery forms
  accepted input; default canonical NoRedirectTransport wraps both usage GET stages.
  One association GET only before explicit status preparation, no extra writes/stores;
  original encoded query bytes, five original message refs, sealed-source ownership,
  14 bad-association variants including503, status triple, equal-revision prepare,
  final callback reentry, credential errors and body waits are checked.
- PASS `association-old-get-regression.txt`: only two affected existing compatibility
  GET tests rerun (default transport and exact original/big integer/null-zero).
  Prior 49d146c other valid evidence is reused, no full suite repeated.
- PASS `association-ios-compile.txt`: unsigned arm64 iOS17 Simulator module compile.
- PASS `association-public-interface.txt.gz`: external positive public API typecheck;
  both closed source constructors are inaccessible to ordinary import (expected
  negative compiler results). Raw probe bytes preserved losslessly, original hash
  recorded in association-provenance.json.
- PASS exact shared693 tree, SDK33 blobs, seven earlier export hashes, unchanged
  module lock and AUTH; provenance in association-provenance.json.

Preserved FAIL / intermediate results:

- association-tests-1.txt: test macro compile FAIL, missing inner try in #require.
- association-tests-2.txt: all 26 expanded new scenarios FAIL at fixture setup because
  staged MESSAGE was queried directly (canonical .queryOnly), no product relaxation.
- association-single.txt: same .queryOnly reproduced in one isolated public-query case.
- Fixed fixture uses beginSubmission→observeUnknown then actual canonical query;
  no POST/network and no constructing accepted source refs.
- association-tests-3.txt: earlier8-function /26-case PASS after fixture repair.
- association-first-build.txt: initial product compile PASS.

Raw log suffix may be .txt.gz when original compiler whitespace required lossless
archival; exact decompressed SHA256 is recorded in association-provenance.json.
No evidence discarded or silently converted to PASS.

Independent Review/Testing/Publish pending. Producer/root HOLD is outside this
consumer's acceptance; real association writer, network, account/keychain/cache,
SQL/provider/cost, CJShell/App integration, UI/device/full Issue9 I remain UNRUN.
No push/PR/merge/issue closure; requested Sol6.1 medium Standard, effective UNKNOWN.
