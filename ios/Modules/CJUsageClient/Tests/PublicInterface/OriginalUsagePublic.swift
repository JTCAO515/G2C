import Foundation
import CJUsageClient
import CJSession
import CJMessageClient

@MainActor func officialUsageSourceExample(model: OriginalUsageViewModel, acceptedRecord: ActionRecord,
    originalLease: Lease, originalSessionOperation: SessionOperation,
    originalActor: Data, originalSelection: UUID, revision: UInt64) async throws {
    let accepted = try model.captureAcceptedMessage(acceptedRecord, lease: originalLease)
    let original = OriginalUsageBinding(acceptedMessage: accepted, sessionOperation: originalSessionOperation,
        actorIdentity: originalActor, selectionGeneration: originalSelection, revision: revision)
    // Host has already installed this SAME binding in its currentBinding callback.
    let associationRead = try model.prepareAssociation(original)
    await model.read(associationRead)
    guard case .sourceReady(let source) = model.state else { return }
    // SECOND explicit user action; shown sequentially only as a compile-time example.
    let statusRead = try model.prepareStatus(source)
    await model.read(statusRead)
}
