# Local history configuration (#198)

The formal `cj_api.local_app:app_from_environment` factory requires `CJ_ENV=local`,
`CJ_LOCAL_CONNINFO` and `CJ_LOCAL_AUTH_DIR`. It loads the existing Trip signing key
and a separate `history-cursor.key` from the auth directory. Missing or malformed
history keys fail startup; no default key or in-memory substitute is generated.

For a new directory:

```sh
CJ_ENV=local uv run --locked python -B scripts/dev_auth.py init .local/dev-auth --invite alice
```

For an existing directory, explicitly add the missing history key:

```sh
CJ_ENV=local uv run --locked python -B scripts/dev_auth.py history-key .local/dev-auth
```

The command creates exactly 32 random bytes with mode 0600 using exclusive creation;
it refuses to overwrite any existing entry. Keep the same file across local API
restarts to preserve cursor validation. Loading rejects links, nonregular files,
lengths other than 32 bytes and modes other than 0600. Keys are never returned in
API responses or logged. This does not authorize production key management.

The existing AEAD codec uses local version/key ID `local-history-v1`, TTL 300 seconds,
token limit 2048 bytes, plaintext limit 512 bytes and binding limit 2048 bytes.
History configuration limits pages to 20, draft bodies to 16384 bytes and private
responses to 1,000,000 bytes. Existing owner/identity/scope checks remain authoritative.
The configuration activates conversation/message pages and draft GET/PUT; PUT still
requires the original expected revision. It does not activate App PUT transport.

`create_local_app` retains optional explicit `history_configuration` for existing
injected tests; its default remains unavailable history. The formal environment
factory always loads the dedicated key. Keep this compatibility seam while the
existing test hosts use it; removal requires migrating and verifying those callers.

Validation:

```sh
uv run --locked python -B -m unittest discover -s backend/cj_api/tests -p test_local_history_config.py
uv run --locked python -B backend/cj_api/tests/local_history_pg.py
uv run --locked python -B scripts/test.py
uv run --locked python -B scripts/pg_suites.py
```

The dedicated PG script creates and tears down a fresh private Unix-socket cluster,
applies the unchanged migration chain, and exercises the formal signed factory as
`cj_m1_runtime`. It covers two-page history, API reconstruction, invalid cursors,
draft revision CAS and cross-account rejection. No cloud, real model or device is
used. Native history UI acceptance remains separately evidenced in #164.
