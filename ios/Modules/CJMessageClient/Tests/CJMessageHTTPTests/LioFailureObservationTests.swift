import CJMessageClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

@MainActor private final class ObservationStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}
@MainActor private final class ObservationCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
@MainActor private final class ObservationFence {
    var checks = 0
    func validate() throws {
        checks += 1
        if checks > 1 { throw RecoveryError.inactive }
    }
}
private actor ObservationResponse: ClientTransport {
    static let reference = "B95744FC-F460-4ED1-B21B-A64D5D34896C"
    var requests = 0
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        requests += 1
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = Self.reference
        return (response, HTTPBody("{}"))
    }
}
@MainActor struct LioFailureObservationTests {
    @Test(arguments: [false, true])
    func responseMetadataSurvivesPostResponseRevocation(send: Bool) async throws {
        let scope = try StorageScope(environment: "synthetic-observation", account: "synthetic-owner")
        let recovery = MessageRecovery(storage: ObservationStore())
        let lease = try recovery.activate(scope)
        let fence = ObservationFence(), response = ObservationResponse()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16384, maximumResponseBytes: 65536)
        let transport = try NoRedirectTransport(interceptedTransport: response, messageEndpoint: endpoint,
                                                validateMessage: { try fence.validate() }, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: ObservationCredentials(), transport: transport)
        if send {
            let original = try LioTimelineWire.Send(messageID: "synthetic-question", text: "Synthetic question", locale: .english)
            await #expect(throws: RecoveryError.inactive) { _ = try await client.submit(original) }
        } else {
            await #expect(throws: RecoveryError.inactive) { _ = try await client.timeline() }
        }
        #expect(client.lastObservation?.kind == (send ? .send : .timeline))
        #expect(client.lastObservation?.httpStatus == 200)
        #expect(client.lastObservation?.serverReference == ObservationResponse.reference)
        #expect(await response.requests == 1)
        #expect(fence.checks == 2)
    }
}
