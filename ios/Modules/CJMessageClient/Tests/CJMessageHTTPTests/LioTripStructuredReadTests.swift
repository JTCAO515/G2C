import CJMessageClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

@MainActor private final class TripReadStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}
@MainActor private final class TripReadCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor TripReadExit: ClientTransport {
    static let reference = "00000000-0000-4000-8000-000000000001"
    struct Call: Sendable {
        let method: HTTPRequest.Method
        let path: String?
        let authorization: String?
        let hasBody: Bool
    }
    private(set) var calls: [Call] = []
    private let status: Int
    private let body: Data

    init(status: Int, body: Data) { self.status = status; self.body = body }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append(Call(method: request.method, path: request.path, authorization: request.headerFields[.authorization],
                          hasBody: body != nil))
        var response = HTTPResponse(status: .init(code: status))
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = Self.reference
        return (response, HTTPBody(self.body))
    }
}

/// #1723 PR-2: the structured trip read sends the trip id alone and bounds what it keeps.
@MainActor struct LioTripStructuredReadTests {
    private func client(_ exit: TripReadExit) throws -> LioTimelineHTTP {
        let scope = try StorageScope(environment: "synthetic-trip-read", account: "synthetic-owner")
        let recovery = MessageRecovery(storage: TripReadStore())
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint, validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: TripReadCredentials(), transport: transport)
    }

    @Test func readSendsOnlyTheTripIDAndReturnsTheResponseAsReceived() async throws {
        let body = Data(#"{"version":"TRIP-structured-read.3","request_id":"x","trip":null}"#.utf8)
        let exit = TripReadExit(status: 200, body: body)
        let response = try await client(exit).readTripStructured(tripID: "trip-1")
        #expect(response == .init(status: 200, requestID: TripReadExit.reference, bytes: body))
        let calls = await exit.calls
        #expect(calls.map(\.path) == ["/v7/trip-structured?trip_id=trip-1"])
        #expect(calls.map(\.method) == [.get])
        #expect(calls.map(\.authorization) == ["Bearer synthetic-only"])
        #expect(calls.map(\.hasBody) == [false])
    }

    @Test(arguments: [401, 400, 503])
    func otherStatusesReturnTheirShortBody(_ status: Int) async throws {
        let body = Data(#"{"request_id":"x","error":{"code":"TRIP_UNAVAILABLE","recovery":"retry_safe_read"}}"#.utf8)
        let response = try await client(TripReadExit(status: status, body: body)).readTripStructured(tripID: "trip-1")
        #expect(response.status == status && response.bytes == body)
    }

    @Test func oversizedBodiesThrow() async throws {
        let large = Data(repeating: 0x20, count: LioTimelineHTTP.tripStructuredMaximumBytes + 1)
        await #expect(throws: (any Error).self) {
            _ = try await client(TripReadExit(status: 200, body: large)).readTripStructured(tripID: "trip-1")
        }
        await #expect(throws: (any Error).self) {
            _ = try await client(TripReadExit(status: 503, body: Data(repeating: 0x20, count: 65_537))).readTripStructured(tripID: "trip-1")
        }
    }

    @Test(arguments: ["", "trip 1", "trip&version=2", "-trip"])
    func anInvalidTripIDSendsNothing(_ id: String) async throws {
        let exit = TripReadExit(status: 200, body: Data("{}".utf8))
        await #expect(throws: MessageHTTPFailure.invalidConfiguration) {
            _ = try await client(exit).readTripStructured(tripID: id)
        }
        #expect(await exit.calls.isEmpty)
    }
}
