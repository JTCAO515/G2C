# P2 same-binding stale exit repair

Parent fca5b6c3259355a097b4ee06e7ea4285a927cb13 is preserved. Review's exact
independent-host.log is retained as review-fca5-repro.log: its final REPRO shows
A's delayed exit clears already accepted B under the same binding. Earlier 17
methods/25 cases did not cover that condition and do not override the HOLD.

The host now issues an opaque MemoryManagementPresentationLifetime per actual
appearance. Its initializer and binding/presentation IDs are private to the host
file. Each SwiftUI detail/manual view retains that lifetime in State onAppear,
then supplies exactly its owned lifetime onDisappear. Re-rendering against B
cannot refresh A's stored lifetime. Row/group/list changes synchronously retire
prior presentation lifetime before a new view even appears. Current-detail
refresh keeps the appearance lifetime, so exiting during an in-flight refresh
still fences its late result. Neither source permission nor management capability
is granted by this UI token.

Removed the unsafe binding-only exit interface from this unpublished candidate;
all own callers and public consumer updated. Client and other owners untouched.

PASS: 19 host methods / 28 parameter-expanded cases in the localized synthetic
Shell harness. Two new methods directly replay the Review sequence and assert B
selection AND detail AND management identity stay intact, both before and after
B's appearance; same-row reopening is also covered. Current B/current reopened
exit still clears detail/selection. Existing held-detail exit and replacement
binding cases pass. Public-only macOS API typecheck passes. No client/PG suite rerun.

Full canonical graph and iOS view compile continue after this repair; they are
not asserted by this repair commit. Original FAILs/fca5 logs remain untouched.
Evidence graph and exact input byte hashes are in p2/inputs.json.
