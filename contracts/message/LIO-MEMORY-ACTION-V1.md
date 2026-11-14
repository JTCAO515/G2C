# LIO memory tags and explicit actions

When the trusted Lio host mounts the original Travel memory-candidate reader,
a completed timeline row has either `memory: null` or
`memory: {"tags":[{"id":"…","kind":"preference","text":"…","target":"…"}]}`.
Tags are current suggestions associated with that exact original message and
execution. The app displays the text and the Remember and Dismiss controls.
Keep the target opaque.

An explicit choice sends UTF-8 JSON as `application/octet-stream` to
`POST /v1/lio/memory/actions`:

```json
{"version":"LIO-memory-action.1","action_id":"choice-53c70195","operation":"remember","target":"<tag target>"}
```

`operation` is `remember` or `dismiss`. The server checks the exact current
suggestion and applies the existing versioned candidate decision. A changed
suggestion requires a fresh timeline read and explicit choice. Reading the
timeline creates no active memory.

The response contains `version: "LIO-memory-action-receipt.1"`, the
`action_id`, and `status` of `remembered`, `dismissed`, or `pending`. If
the result remains uncertain, use the same original JSON body with
`POST /v1/lio/memory/receipt`. This endpoint only reads the exact receipt.
The target stays in the body so the reviewed text never goes in the URL.
A pending receipt grants no retry permission. Both routes require the
current signed Lio identity and return `Cache-Control: no-store`.
