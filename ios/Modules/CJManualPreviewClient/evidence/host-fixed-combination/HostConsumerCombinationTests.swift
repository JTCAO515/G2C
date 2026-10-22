import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP
@testable import CJManualPreviewClient

private struct HostInput: ClientTransport {
    let transport: NoRedirectTransport
    let fields: [(String, String)]
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        var injected = request
        for (name, value) in fields {
            injected.headerFields.append(HTTPField(name: HTTPField.Name(name)!, value: value))
        }
        return try await transport.send(injected, body: body, baseURL: baseURL, operationID: operationID)
    }
}
@Suite @MainActor struct HostConsumerCombinationTests {
    @Test(arguments: [0, 1, 2, 3, 4, 5]) func hostInputIsRejectedByActualSharedCapabilityAndDraftRemains(_ variant: Int) async throws {
        let variants = [[("Host", "other.invalid")], [("HOST", "preview.invalid")],
                        [("hOsT", "preview.invalid:443")], [("host", "")],
                        [("Host", "preview.invalid"), ("host", "other.invalid")],
                        [("HOST", "preview.invalid"), ("hOsT", "preview.invalid")]]
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original)))
        var sharedChecks = 0
        let editor = try PreviewEditor(trip: h.trip, source: h.snapshot, endpoint: h.endpoint,
            session: h.session, operation: h.operation, credentials: { _ in "synthetic" },
            transportFactory: { validate in
                let transport = try NoRedirectTransport(interceptedTransport: wire,
                    previewEndpoint: h.endpoint, validatePreview: { sharedChecks += 1; try validate() })
                return HostInput(transport: transport, fields: variants[variant])
            })
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(await wire.calls.isEmpty)
        #expect(sharedChecks == 0)
        #expect(editor.display()?.status == .unavailable)
        #expect(editor.display()?.preview == nil)
        #expect(editor.display()?.title == h.original.document.title)
        #expect(work.request.original_content_utf8_base64 == h.original.content_utf8_base64)
    }
}
