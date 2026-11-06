# Typed Memory host composition

`cj_memory.typed_api.register_typed_routes(app, database=..., auth_dir=...,
configuration=...)` installs the existing seven `/v2` save, read, management
and withdrawal routes in an existing CJ API app. The app must retain CJ's trace
and private-response middleware. Register these routes once before serving.

The trusted host provides its existing scoped runtime `LocalDatabase` (including
the B-owned `SupabaseTestDatabase` subclass), constructed with
`travel_context=True` and the original run context and transaction guard when
required by that host. The registrar uses this same database for account
retirement, owner-scoped Memory repositories and current Message/Travel leases.
It does not construct another connection or change the injected database's
capabilities. The host owns cloud TLS, runtime role, release guard and admission
configuration; an HTTP request cannot configure these dependencies.

Load the existing `local-memory-typed.1` policy with
`cj_memory.typed_local.load_typed_configuration` from the host's private operator
file (owned regular file, no group/world access). Policy profiles are keyed by
the existing signed JWT subjects. `subjects`/`slots` grant only the explicit
collection scope; `travel_contexts` contains explicit allowed Travel IDs, not
conversation IDs. `semantic_resolved` attests canonical subject/slot resolution,
not the truth of text or confirmation of inference. No permissive profile is
created by the registrar.

`CJ_ENV=local`, fixed JWT issuer/audience/key, current invited/account checks,
source expiry, byte limits and all existing commit/withdrawal fences remain in
force. This seam does not enable the closed legacy Memory-management host or
change any frozen wire/configuration version. `create_local_typed_app` retains
its original signature and Unix-only `LocalDatabase` construction for existing
local consumers.

Local restricted-PG tests prove composition and guards only. B must separately
verify its approved cloud host; actual model recall and quality remain #32.
