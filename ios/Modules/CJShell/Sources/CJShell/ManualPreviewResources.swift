import Foundation
import CJManualPreviewClient
import CJTripClient
import CJMessageHTTP
import CJSession

/// Existing trusted read resources. This does not activate a transport or grant save permission.
@MainActor public struct ManualPreviewResources {
    let endpoint: MessageEndpoint
    let credentials: TripCredentialCallback
    let requestTimeout: TimeInterval
    let resourceTimeout: TimeInterval
    public init(endpoint: MessageEndpoint, credentials: @escaping TripCredentialCallback,
                previewRequestTimeout: TimeInterval, previewResourceTimeout: TimeInterval) throws {
        guard previewRequestTimeout > 0, previewResourceTimeout > 0,
              previewRequestTimeout.isFinite, previewResourceTimeout.isFinite else { throw PreviewFailure.invalidInput }
        self.endpoint = endpoint; self.credentials = credentials
        requestTimeout = previewRequestTimeout; resourceTimeout = previewResourceTimeout
    }
}
public enum ManualEditorLoadState: Equatable, Sendable { case unavailable, idle, loading, missing, ready, failed }
public struct ManualPreviewEntry: Identifiable, Hashable, Sendable {
    public let id: UUID
    init() { id = UUID() }
}
@MainActor public struct ManualEditorWork {
    let context: TripContainerAction
    let request: TripDetailSnapshotRequest
    let token: UUID
    let resources: ManualPreviewResources
}
// Internal test injection only. The public host always constructs the real public editor
// with its per-work readonly NoRedirectTransport; consumers cannot select another networking path.
typealias ManualEditorFactory = @MainActor (TripClient, AcceptedTripDetailSnapshot, SessionLifecycle, SessionOperation, ManualPreviewResources) throws -> PreviewEditor
