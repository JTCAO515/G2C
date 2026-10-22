# Fixed CJSession interface consumption

Read-only source `ef2c7da41cce9bc994fa7859c29dddd5f915a978`:
`ios/Modules/CJAuth/Sources/CJSession/SessionLifecycle.swift`, SESSION-STORE.md and
Package.swift. No moving Keychain source, package import or real credential access.
Interface `CJ-SESSION-STORE@0.1.0-rc.1` is a candidate; typecheck is not independent acceptance.

Compatible semantic seams:

- SessionNamespace.environment is a host-allocated UUID; its slot is a credential slot,
  not necessarily a business account ID. Message StorageScope is only a local partition.
  No direct slot→account mapping inferred. Host must supply approved environment and
  verified stable account mapping; an SDK session blob is never an encryption key.
- SessionOperation/isCurrent bind session load/save instance/generation/purpose; they
  are not general private-message request tokens. Message Lease/Operation are local
  fences with no AUTH authority. No copied SessionOperation type or fake adapter exists.
- Host should invalidate message state BEFORE calling SessionLifecycle.clear on logout/
  switch/invalidation. If clear fails/blocked, keep message state inactive and do not
  activate/restore it. A later successful clear does not itself authenticate a new user.
- loadedNeedsVerification/saved/missing/cleared do not permit business; the fixed
  canUseRestrictedBusiness is always false. Message activate must wait for a separate
  real verified identity/eligibility gate. Never treat successful local load as login.
- noteNetworkUnknown preserves credential storage/generation; likewise preserve encrypted
  original actions and do not reset queryRequired/notObserved to staged. Hide/fence message
  access while host cannot establish permission. Revalidation uses a new local activation
  lease; no credential deletion or server rollback is claimed.
- userInitiatedOnly is honored: this package has no automatic launch restore hook. The
  host initiates activate after its own verified lifecycle and approved local-data policy.

Missing exact inputs before a concrete bridge: verified account/environment mapping,
private-data access decision/notification, lifecycle clear/blocked host coordination,
and message AES key provision/revocation/rotation from an approved secure provider.
SessionPersistence stores session material only; it does not yet satisfy
MessageEncryptionKeyProvider. We will not reinterpret session bytes as a key, install a
second AUTH authority, or expose production account state through the test provider.

Conclusion: local core compatible with the fixed lifecycle semantics; direct integration
PENDING the above actual host/key interfaces. No source dependency added, no guessed fields.
Independent CJ007/CJ009 acceptance, real Keychain, true SDK/service and device remain UNRUN.

## Independent message-key interface delta

Fixed f1ce075e4b3f26e6c65bfe4b2fa8bcec8291a552 now supplies CJ-MESSAGE-KEYS interface,
separate from session credentials. See KEY-BINDING.md for exact read-only adapter,
authenticated key-ID v2 format, explicit legacy refusal and host lifecycle gaps. This
supersedes the earlier absence of an interface, not the pending real implementation or
host mapping/entitlement acceptance. No session token becomes an AES key.
