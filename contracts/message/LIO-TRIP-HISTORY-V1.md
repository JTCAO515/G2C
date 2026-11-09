# LIO-trip-history.1 and LIO-trip-undo.1

The signed internal-beta Lio subject can read its selected itinerary with
`GET /v1/lio/trip`. The response contains `version: "LIO-trip-history.1"`,
`current`, `history`, `undo_target`, and `next_before`. Itinerary cards use
the Lio timeline card shape. A subject with no saved itinerary receives
`current: null` and an empty history. A saved itinerary's first page contains
the current card and up to nine prior cards, newest first. An older page
requested with `before=<next_before>` returns up to ten prior cards and null
current and undo fields. The cursor is an opaque string for the app.

After the second saved version, the first page includes an opaque
`undo_target` identifying the exact version shown in the app. The user can
tap Undo to send a UTF-8 JSON body with content type
`application/octet-stream` to `POST /v1/lio/trip/undo`:

```json
{"version":"LIO-trip-undo.1","action_id":"undo-53c70195","target":"<undo_target>"}
```

Undo checks the original selected itinerary, its current version, fixed
items, and current travel requirements. A successful undo appends the
previous itinerary as a new saved version and preserves history. An out-of-date
target is refused. Keep the original action ID and target together.

The reply has `version: "LIO-trip-undo-receipt.1"`, `action_id`, and
`committed: true`. If the server loses the result of an attempted commit, it
checks the original receipt before replying. If the result remains uncertain,
the app can read `GET /v1/lio/trip/undo?action_id=…&target=…` with the original
pair. A read with `committed: false` does not establish that the original
action failed. Keep polling that receipt and refresh the current itinerary
after a verified commit. The app shows the itinerary and the Undo button
without displaying the cursor, target, or action ID.
