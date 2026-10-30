import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class TravelReadStorage: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot,scope: StorageScope) throws { }
}
@MainActor private final class TravelReadCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope,lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor TravelReadWire: ClientTransport {
    let id: String
    let timestamp: String
    let after: @Sendable () async -> Void
    var count = 0
    init(id: String,timestamp: String = "2026-10-30T11:12:13.123456Z",after: @escaping @Sendable () async -> Void = {}) {
        self.id = id;self.timestamp = timestamp;self.after = after
    }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        count += 1
        #expect(operationID == "getTravelContext" && request.method == .get)
        #expect(request.path == "/v1/travel-contexts/0123456789abcdef0123456789abcdef")
        await after()
        let trace = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json";response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        let raw = try JSONSerialization.data(withJSONObject: ["request_id":trace,"version":"TRAVEL-context.1","travel_context":["id":id,"version":2,"active":true,"created_at":timestamp]])
        return (response,HTTPBody(raw))
    }
}
@MainActor struct TravelContextReadTests {
    let id = "0123456789abcdef0123456789abcdef"
    private func setup(_ wire: TravelReadWire) throws -> (MessageRecovery,Lease,MessageHTTPClient) {
        let recovery = MessageRecovery(storage: TravelReadStorage())
        let scope = try StorageScope(environment: UUID().uuidString,account:"synthetic")
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client = MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:TravelReadCredentials(),interceptedTestTransport:wire)
        return (recovery,lease,client)
    }
    @Test(arguments: ["2026-10-30T11:12:13Z","2026-10-30T11:12:13.123456Z"])
    func readsExactOwnedIdentityAndFencesResultToClient(timestamp: String) async throws {
        let wire = TravelReadWire(id:id,timestamp:timestamp);let (_,lease,client) = try setup(wire)
        let result = try await client.readTravelContext(id:id,lease:lease)
        #expect(result.value.id == id && result.value.version == 2 && result.value.active)
        try client.validateRead(result,lease:lease)
        let (_,otherLease,other) = try setup(wire)
        #expect(throws: RecoveryError.inactive) { try other.validateRead(result,lease:otherLease) }
    }
    @Test func wrongIdentityIsNotReboundToTheRequestedTravel() async throws {
        let wire = TravelReadWire(id:String(repeating:"f",count:32));let (_,lease,client) = try setup(wire)
        await #expect(throws: MessageHTTPFailure.invalidResponse) { try await client.readTravelContext(id:id,lease:lease) }
    }
    @Test func lateReadCannotPublishAfterLeaseInvalidation() async throws {
        let recovery = MessageRecovery(storage: TravelReadStorage());let scope = try StorageScope(environment:UUID().uuidString,account:"synthetic")
        let lease = try recovery.activate(scope)
        let wire = TravelReadWire(id:id,after:{ await MainActor.run { recovery.invalidate() } })
        let endpoint = try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client = MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:TravelReadCredentials(),interceptedTestTransport:wire)
        await #expect(throws: RecoveryError.inactive) { try await client.readTravelContext(id:id,lease:lease) }
    }
    @Test(arguments: ["", "0123456789ABCDEF0123456789ABCDEF", "../context", "0123456789abcdef0123456789abcdef?owner=x"])
    func invalidIDsNeverDispatch(value: String) async throws {
        let wire = TravelReadWire(id:id);let (_,lease,client) = try setup(wire)
        await #expect(throws: RecoveryError.invalidInput) { try await client.readTravelContext(id:value,lease:lease) }
        #expect(await wire.count == 0)
    }
}
