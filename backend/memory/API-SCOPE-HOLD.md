# API Memory scope fence

`ApiMemoryScopeHolder(database, api_typed_configuration).hold(message_context)`
uses the API's existing TypedConfiguration. The trusted caller supplies its
actual issued M frame (principal, owner scope, throwing check() -> None), such
as C's HeldHistory; a public epoch/profile DTO is not that frame.

The caller holds M before entering. The holder locks the existing active
Memory scope through Repository.transaction / lock_scope, and yields epoch
point data plus check(). It performs no namespace initialization, item read,
collection/model call or write. Missing/inactive scope, missing/expired policy,
changed owner/configuration, expired or cross-thread handle withholds the hold.
A commit completion unknown remains RuntimeUnknown, not a new action permit.

C/L must separately compose the actual current planning-profile fence and their
NEEDS/Trip sources and signed action. Ordering is M -> Memory -> source/NEEDS ->
Trip. Call held.check() in the final source check while the hold is still active
through the Trip commit. The holder grants no Trip write, PlanNow or item access.
Do not acquire a second M or competing Memory transaction inside this hold.
Historical Trip fields cannot initialize current Memory/profile state.

Native tests use an actual signed MESSAGE effect lease and an explicit native
history-disable action to prepare the test Memory namespace. A real concurrent
Memory holder blocks, then releases; epoch/active remain unchanged. The missing
namespace case stays missing. This evidence is not a complete HTTP4 undo, a
production grant or a live Hong Kong verification.
