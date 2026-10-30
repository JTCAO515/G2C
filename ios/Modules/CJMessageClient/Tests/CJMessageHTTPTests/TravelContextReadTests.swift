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
    let active: Bool
    let after: @Sendable () async -> Void
    var count = 0
    init(id: String,timestamp: String = "2026-10-30T11:12:13.123456Z",active: Bool = true,after: @escaping @Sendable () async -> Void = {}) {
        self.id = id;self.timestamp = timestamp;self.active = active;self.after = after
    }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        count += 1
        #expect(operationID == "getTravelContext" && request.method == .get)
        #expect(request.path == "/v1/travel-contexts/0123456789abcdef0123456789abcdef")
        await after()
        let trace = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json";response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        let raw = try JSONSerialization.data(withJSONObject: ["request_id":trace,"version":"TRAVEL-context.1","travel_context":["id":id,"version":2,"active":active,"created_at":timestamp]])
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


@MainActor private final class TravelSelectionBox { var model: TravelSelectionModel? }
extension TravelContextReadTests {
    @Test func noConfiguredTravelsStillRequiresExplicitNoneAndNeverDispatches() async throws {
        let wire = TravelReadWire(id:id),(_,lease,client) = try setup(wire)
        let model = try TravelSelectionModel(ids:[],client:client,lease:lease,isCurrent:{true})
        #expect(model.ids.isEmpty)
        #expect(throws:RecoveryError.queryOnly) { try model.capture() }
        await model.selectTravel(id)
        #expect(await wire.count == 0)
        #expect(throws:RecoveryError.queryOnly) { try model.capture() }
        try model.selectNone()
        #expect(try model.capture().context == nil)
        #expect(await wire.count == 0)
    }
    @Test func explicitNoneAndOwnedTravelAreDifferentCapturesAndRetireOldChoice() async throws {
        let wire = TravelReadWire(id:id),(_,lease,client) = try setup(wire)
        let model = try TravelSelectionModel(ids:[id],client:client,lease:lease,isCurrent:{true})
        #expect(throws:RecoveryError.queryOnly) { try model.capture() }
        try model.selectNone();let none = try model.capture();#expect(none.context == nil)
        await model.selectTravel(id)
        let travel = try model.capture();#expect(travel.context?.value.id == id && travel.context?.value.version == 2)
        #expect(throws:(any Error).self) { try model.validate(none) }
        try model.validate(travel)
        let other = try TravelSelectionModel(ids:[id],client:client,lease:lease,isCurrent:{true})
        try other.selectNone()
        #expect(throws:(any Error).self) { try other.validate(travel) }
    }
    @Test func retiredScopeRemovesChoicesAndNeverTurnsIntoExplicitNone() throws {
        let wire = TravelReadWire(id:id), (recovery,lease,client) = try setup(wire)
        let model = try TravelSelectionModel(ids:[id],client:client,lease:lease,isCurrent:{true})
        try model.selectNone();let capture = try model.capture();recovery.invalidate()
        guard case .unavailable = model.state else { Issue.record("stale scope still visible");return }
        #expect(model.ids.isEmpty)
        #expect(throws:(any Error).self) { try model.capture() }
        #expect(throws:(any Error).self) { try model.validate(capture) }
    }
    @Test func unknownOrInactiveTravelNeverBecomesNoneOrDispatchPermission() async throws {
        let wire = TravelReadWire(id:id,active:false),(_,lease,client) = try setup(wire)
        let model = try TravelSelectionModel(ids:[id],client:client,lease:lease,isCurrent:{true})
        await model.selectTravel(String(repeating:"f",count:32));#expect(await wire.count == 0)
        #expect(throws:(any Error).self) { try model.capture() }
        await model.selectTravel(id);#expect(await wire.count == 1)
        guard case .unavailable = model.state else { Issue.record("inactive travel accepted");return }
        #expect(throws:(any Error).self) { try model.capture() }
    }
    @Test func lateTravelReadCannotReplaceExplicitLaterNone() async throws {
        let box = TravelSelectionBox()
        let wire = TravelReadWire(id:id,after:{ await MainActor.run {
            do { let model = try #require(box.model);try model.selectNone() }
            catch { Issue.record(error) }
        } })
        let (_,lease,client) = try setup(wire)
        let model = try TravelSelectionModel(ids:[id],client:client,lease:lease,isCurrent:{true});box.model = model
        await model.selectTravel(id)
        guard case .none = model.state else { Issue.record("late read overwrote later explicit choice");return }
        #expect(try model.capture().context == nil)
    }
}
