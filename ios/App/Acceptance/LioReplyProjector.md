# Ordinary Home text projection (local acceptance producer)

`build_lio_reply_projector.py --source-root "$PINNED_CHECKOUT" --output "$NEW_PRIVATE_DIRECTORY"`
builds the actual `LioReplyMarkdown.render` function from a clean iOS checkout. The
program listed in `projector.json` reads one JSON request on stdin and writes one
JSON result on stdout. It has no network, credentials, message submission or App
control path.

Input is `LIO-reply-projection-request.1` with `app`, `raw_utf8`, `input_sha256`.
The App dictionary must contain the pinned `source_commit` and matching
`renderer_source_sha256`. Output is `LIO-reply-projection.1`, with the same App,
source/input digests, `rejected`, `rendered_utf8` and `rendered_sha256`.
Invalid input/source bindings exit nonzero with no reply text. A public-display
rejection is explicit, not an invented answer. No whitespace normalization,
TextBlock reconstruction or second Markdown parser is used.

The renderer digest is SHA256 of the canonical JSON array (sorted object keys,
compact separators, UTF-8) of relative path/SHA256 records, in this order:

- `LioReplyMarkdown.swift`
- `LioPublicDisplay.swift`
- `LioTheme.swift`
- `LioStreamingText.swift`

The full relative paths and individual hashes are in the manifest. They bind the
ordinary one-render-and-prefix path and its existing public-display guard.
The executable digest is recorded separately. Keep its generated SwiftPM package
and resource bundles together; do not move just the binary.

This host executable runs macOS Foundation. Its environment is reported honestly;
it is not proof of iOS Foundation behavior, a tested App artifact, UI success,
Hong Kong eligibility, device acceptance or release permission. Echoing an App
dictionary does not attest those fields. C must still compare the actual final
`lio.answer` AX bytes with this exact projection for every actual read, and must
verify the separate tested App/source/artifact and producer qualification.

Synthetic controls verify ordinary Chinese/English text, internal UUID and tool
rejections, and wrong input/source bindings. Actual private provider text belongs
to the authorized C reader and must not be pasted into chats or test logs.
