# Lio internal sign-in and legacy starter data

Refs #1124 / #1048. The ordinary Lio App and the development shell share the
existing account lifetime; their business selections are not authentication.

For `G2C_DEMO_BETA` + `G2C_LIO_APP`, the fixed-origin invitation response produces
the local Keychain envelope `LIO-demo-session.1`: `version` and the original
validated `grant`. It has no conversation, NEEDS or travel starter selection.
The unchanged protected session check must still succeed before the credential
is saved and the owner-scoped Root activates. A grant or a welcome message alone
does not authorize business access or prove successful sign-in.

Lio's composition uses the existing typed-memory configuration with an empty
travel-choice list and no preselected NEEDS. An empty list is an already supported
choice state, not a travel identifier, a selection, or permission to write.
Trips, memory, cleanup, message journals and HTTP clients retain their existing
account, session, lease, currentness and prior-original checks. No server starter,
Trip, conversation or business message is created to complete sign-in.

Versionless stored envelopes still require and validate their original legacy
composition. The development shell keeps its old protected starter reads. New
Lio envelopes are rejected outside the Lio build; unknown or mixed local envelope
versions fail closed. The credential namespace and original stored records are
not migrated or cleared. Renewal preserves the envelope mode and retains the
same owner and the original expiry checks; a newer envelope requires a compatible
App to restore it, rather than being reinterpreted by an older reader.

Response/setup failures have a separate account presentation state from network
failures. Existing on-device notes add the `signIn` stage, HTTP status and a
validated service reference. Notes never contain credential bytes, response
bodies, account identifiers or raw error descriptions. Cancellation does not
publish a late sign-in problem.

Local integration uses the existing B691 transport boundary in a fresh owned
simulator. Only the generated fixture session adds its synthetic transport class
and marker header; the product endpoint, decoder and Root remain the real ones.
The old-client control returns four successful responses with no legacy starter
data and must retain its original failure. These controls do not replace the
next real Hong Kong window, bilingual seven-item smoke or physical-device proof.
