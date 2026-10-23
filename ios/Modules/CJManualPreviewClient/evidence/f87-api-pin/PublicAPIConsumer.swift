// Compile-only host consumer; never invoked and never sends a request.
import SwiftUI
import CJManualPreviewClient
import CJTripClient
import CJSession
import CJMessageHTTP

@MainActor func originalSelectionPreview(
    trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
    session: SessionLifecycle, operation: SessionOperation,
    credentials: @escaping TripCredentialCallback,
    requestTimeout: Double, resourceTimeout: Double
) throws -> ManualPreviewView {
    let editor = try PreviewEditor(trip: trip, source: source, endpoint: endpoint,
        session: session, operation: operation, credentials: credentials,
        previewRequestTimeout: requestTimeout, previewResourceTimeout: resourceTimeout)
    let work = try editor.preparePreview()
    Task { await editor.perform(work) }
    return ManualPreviewView(editor: editor, language: .chinese)
}
@MainActor func suppliedTransportPreview(
    trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
    session: SessionLifecycle, operation: SessionOperation,
    credentials: @escaping TripCredentialCallback, transport: NoRedirectTransport
) throws -> PreviewEditor {
    try PreviewEditor(trip: trip, source: source, endpoint: endpoint,
        session: session, operation: operation, credentials: credentials, liveTransport: transport)
}
