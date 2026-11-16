import CJLioUser

/// Called only for the new authenticated host; this metadata grants no sending authority.
@MainActor func restoreLioChatPosition(_ position: LioChatContinuity, store: LioChatPositionStore,
                                     previous: LioChatContinuity? = nil) throws {
    if let bytes = try store.load() { try position.restorePosition(bytes) }
    if let previous { position.inherit(previous) }
    position.bindPositionWriter { try store.save($0) }
    position.retryKeepingPosition()
}
