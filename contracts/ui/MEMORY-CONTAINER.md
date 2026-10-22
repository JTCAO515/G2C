# CJ006 Memory tab container

The trusted composition root may inject `MemoryContainerHost` into `ShellView`, tied to the exact same `ShellState`. Default construction is unconfigured: no client, identity, endpoint, credential, directory, key, manual option policy, or write grant is fabricated. `MemoryContainerBinding` requires the actual `MemoryClient`, canonical `MemoryBinding`, original ShellGeneration and the same current-binding callback used by the client. The synthetic marker is disclosure only, never permission.

The Memory tab embeds CJMemoryClient's groups, items, detail, manual form and receipt-status components. Reads are explicit user actions; init, language change and foreground entry do not automatically fetch or rebind. Account, language and help remain in Memory. Old static group routes are retained for existing consumers but are no longer the main listing.

## Original action and private lifetime

Each view captures a `MemoryContainerAction` before creating its Task. Binding instance + operation epoch + shell generation + canonical current binding are checked before dispatch and after await/callback. Requests serialize because the canonical client owns one operation generation. Old queued actions cannot retarget a newer binding, and old results cannot clear or overwrite B's rows/busy state. Callbacks are checked again after returning.

Account invalidation clears own private UI before resource callbacks, invalidates Memory before message/history callbacks, and rechecks shell generation before further cleanup. Leaving active scene state clears private memory data and removes the manual form; no foreground rebind occurs. Each installed binding has a new form identity, so a same-value canonical binding cannot revive a prior form's draft. This is local presentation cleanup, not remote deletion/revocation.

## Canonical reads and recovery

- Groups and item IDs retain exact original UTF-8 identities; subjects/statuses select actual returned rows, not local category guesses. Producer 884 supplies byte-distinct SwiftUI row identity.
- `listMemories` is a global keyset list. The container filters loaded pages by exact subject/status, follows only canonical opaque cursors, and retains next-page access even if a fetched page has no matching group items. Empty/null canonical terminal page ends pagination; group count is not used to infer completion.
- Detail displays the actual canonical item/status/source/version/occurred/recorded fields. Candidate is not confirmed fact; historical saved receipt is not current-effective evidence.
- Existing original pending records are read only through the injected canonical secure store. Missing store/key/corrupt data is an explicit failure, never empty success or key rotation. Query accepts only an original published pending operation ID using byte equality, uses domain original bytes/hash, and labels its operation alongside saved/candidate/notObserved/unknown. No resend or new operation ID is created by recovery.
- Production POST remains closed. The actual manual form is embedded only with an existing binding/options and disabled; `submitManual` also rejects with `liveWriteUnavailable` before touching client, storage or credentials. There is no app Boolean to open writes. Enabling a future producer write capability requires separate explicit approved integration.

These components establish source integration, not a trusted live composition root, real account flow, complete memory editing/deletion/next-answer behavior or device acceptance.
