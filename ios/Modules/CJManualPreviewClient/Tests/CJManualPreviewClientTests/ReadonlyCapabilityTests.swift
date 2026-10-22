import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP
@testable import CJManualPreviewClient

@Suite @MainActor struct ReadonlyCapabilityTests {
    private func editor(_ h: Harness, wire: Wire,
                        hook: (@MainActor @Sendable (Int) throws -> Void)? = nil) throws -> PreviewEditor {
        try PreviewEditor(trip: h.trip, source: h.snapshot, endpoint: h.endpoint,
            session: h.session, operation: h.operation, credentials: { _ in "synthetic" },
            transportFactory: { validate in
                var calls = 0
                return try NoRedirectTransport(interceptedTransport: wire, previewEndpoint: h.endpoint,
                    validatePreview: {
                        calls += 1
                        try hook?(calls)
                        try validate()
                    })
            })
    }
    @Test func exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest() async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original, titleSelected: true)))
        var checks = 0
        let state = try editor(h, wire: wire, hook: { checks = $0 })
        try state.selectTitle(true)
        let work = try state.preparePreview(); await state.perform(work)
        #expect(state.display()?.status == .local)
        #expect(state.display()?.preview?.can_save == false)
        #expect(await wire.calls == [work.bytes])
        #expect(checks == 3)
        #expect(work.bytes.range(of: Data("e\u{301}".utf8)) != nil)
        #expect(work.request.original_content_utf8_base64 == h.original.content_utf8_base64)
        #expect(work.request.expected_version == 7)
    }
    @Test(arguments: [1, 2, 3]) func sharedValidatorFencesReentrantEditABAAtEveryPoint(_ point: Int) async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original)))
        var state: PreviewEditor!
        var fired = false
        state = try editor(h, wire: wire, hook: { count in
            if count == point {
                h.callback = {
                    h.callback = nil; fired = true
                    try? state.selectTitle(true); try? state.setTitle("temporary"); try? state.setTitle(h.original.document.title)
                }
            }
        })
        let work = try state.preparePreview(); await state.perform(work)
        #expect(fired)
        #expect(state.display()?.status == .editing); #expect(state.display()?.preview == nil)
        #expect(await wire.calls.count == (point == 1 ? 0 : 1))
    }
    @Test(arguments: [false, true]) func sharedResponseAwaitAndBodyRetirementKeepNewDraft(_ body: Bool) async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: body ? nil : gate, bodyGate: body ? gate : nil)
        let state = try editor(h, wire: wire); let work = try state.preparePreview()
        let task = Task { await state.perform(work) }; await gate.wait()
        try state.selectTitle(true); try state.setTitle("New draft at shared await")
        await gate.release(); await task.value
        #expect(state.display()?.title == "New draft at shared await")
        #expect(state.display()?.status == .editing); #expect(state.display()?.preview == nil)
    }
    @Test func sharedSourceSessionAndFactoryRetirementCannotDispatch() async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original)))
        let state = try editor(h, wire: wire, hook: { _ in _ = try h.session.beginTrustedSDKSave() })
        let work = try state.preparePreview(); await state.perform(work)
        #expect(await wire.calls.isEmpty); #expect(state.display() == nil)

        let other = try Harness(); try await other.load()
        let otherWire = Wire(try response(preview(other.original)))
        let retired = try PreviewEditor(trip: other.trip, source: other.snapshot, endpoint: other.endpoint,
            session: other.session, operation: other.operation, credentials: { _ in "synthetic" },
            transportFactory: { validate in
                other.trip.invalidateDetailSnapshots()
                return try NoRedirectTransport(interceptedTransport: otherWire, previewEndpoint: other.endpoint, validatePreview: validate)
            })
        let old = try retired.preparePreview(); await retired.perform(old)
        #expect(await otherWire.calls.isEmpty); #expect(retired.display() == nil)
    }
    @Test func sharedExactCapabilityStillRefusesActionSaveAndPathScopeExpansion() async throws {
        let h = try Harness(); try await h.load(); let wire = Wire(Data("{}".utf8))
        let transport = try NoRedirectTransport(interceptedTransport: wire, previewEndpoint: h.endpoint,
            validatePreview: { try h.trip.validateDetailSnapshot(h.snapshot) })
        for (path, method, operation) in [("/v1/trip-actions", HTTPRequest.Method.post, "actOnTripProposal"),
            ("/v1/trip-manual-previews?scope=all", .post, Operations.previewManualTripEdit.id),
            ("/v1/trip-manual-previews", .put, Operations.previewManualTripEdit.id)] {
            var request = HTTPRequest(method: method, scheme: nil, authority: nil, path: path)
            request.headerFields[.contentType] = "application/json"
            await #expect(throws: MessageHTTPFailure.self) {
                try await transport.send(request, body: HTTPBody("{}"), baseURL: h.endpoint.url, operationID: operation)
            }
        }
        #expect(await wire.calls.isEmpty)
    }
    @Test func publicOptInRequiresExplicitFiniteTimeoutsWithoutSending() async throws {
        let h = try Harness(); try await h.load()
        _ = try PreviewEditor(trip: h.trip, source: h.snapshot, endpoint: h.endpoint,
            session: h.session, operation: h.operation, credentials: { _ in "synthetic" },
            previewRequestTimeout: 1, previewResourceTimeout: 2)
        for invalid in [0.0, -1.0, .infinity, .nan] {
            #expect(throws: PreviewFailure.invalidInput) {
                try PreviewEditor(trip: h.trip, source: h.snapshot, endpoint: h.endpoint,
                    session: h.session, operation: h.operation, credentials: { _ in "synthetic" },
                    previewRequestTimeout: invalid, previewResourceTimeout: 2)
            }
        }
    }
}
