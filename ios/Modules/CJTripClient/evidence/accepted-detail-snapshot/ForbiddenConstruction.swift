// Expected compile failure: a UI/consumer cannot create either accepted proof or original request.
import CJTripClient
let forgedSnapshot = AcceptedTripDetailSnapshot()
let forgedOriginal = TripDetailSnapshotRequest()
