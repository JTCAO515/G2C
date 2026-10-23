import Foundation
import Testing
import CJRunClient
import CJMessageHTTP

/// External-consumer imports only: no internal interceptor or write capability.
@MainActor struct SDKPublicConstructionTests {
    @Test func publicConstructionRemainsClosedWithoutOriginalSource() throws {
        var credentialCalls = 0
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
                                           maximumRequestBytes: 1024, maximumResponseBytes: 8192)
        let transport = try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 2)
        let model = try RunDisplayModel(endpoint: endpoint, maximumMessageIDBytes: 512,
                                       maximumTextBytes: 4096, credentials: { _ in
            credentialCalls += 1
            return nil
        }, liveReadTransport: transport)
        _ = RunDisplayView(model: model, language: .english)
        #expect(model.prepareRead() == nil)
        #expect(credentialCalls == 0)
        if case .unselected = model.state {} else { Issue.record("Unbound public construction must stay closed") }
    }
}
