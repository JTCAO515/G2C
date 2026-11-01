import Foundation
import Observation
import CJTripClient
import CJAPI
import CJMessageHTTP
import CJMessageKeys
import OpenAPIRuntime
import HTTPTypes

@MainActor public final class NeedsPlanningRead {
    public let value: NeedsPlanningDiscovery
    fileprivate let owner: UUID
    fileprivate let validate: @MainActor () throws -> Void
    fileprivate init(value: NeedsPlanningDiscovery, owner: UUID, validate: @escaping @MainActor () throws -> Void) {
        self.value = value; self.owner = owner; self.validate = validate
    }
}
@MainActor public final class NeedsPlanningWork {
    public let actionID: String
    fileprivate let owner: UUID
    fileprivate let original: NeedsPlanningOriginal
    fileprivate let read: NeedsPlanningRead
    fileprivate let proof: ScopedJournal<NeedsPlanningOriginal>.Durability
    fileprivate var started = false
    fileprivate init(owner: UUID, original: NeedsPlanningOriginal, read: NeedsPlanningRead, proof: ScopedJournal<NeedsPlanningOriginal>.Durability) {
        self.owner = owner; self.original = original; self.read = read; self.proof = proof; actionID = original.actionID
    }
}
public struct NeedsPlanningOriginalDisplay: Identifiable, Sendable {
    public var id: String { actionID }
    public let actionID: String
    public let kind: NeedsPlanningAction.Kind
    public let candidate: NeedsPlanningCandidate
    public let discovery: NeedsPlanningDiscovery
}
public enum NeedsPlanningResult: Sendable {
    case confirmed(NeedsPlanningReceipt), unknown, rejected(Int)
}

/// One account/session lifetime. New writes require an actual protected read,
/// one explicit choice and durable bytes. Existing originals expose GET only.
@MainActor public final class NeedsPlanningClient {
    private let endpoint: MessageEndpoint
    private let binding: TripBinding
    private let credentials: TripCredentialCallback
    private let validate: @MainActor () throws -> Void
    private let transportFactory: @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let originals: ScopedJournal<NeedsPlanningOriginal>
    private let settlements: ScopedJournal<NeedsPlanningSettlement>
    private let owner = UUID()
    private var staging = UUID()
    public convenience init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
        validate: @escaping @MainActor () throws -> Void, directory: URL, receiptDirectory: URL,
        expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        let originals = try ScopedJournal<NeedsPlanningOriginal>(directory: directory, maximumBytes: 6_000_000, maximumRecords: 100,
            binding: binding, expectedKeyID: expectedKeyID, domain: "CJNeedsPlanningOriginal.1", provider: provider)
        let settlements = try ScopedJournal<NeedsPlanningSettlement>(directory: receiptDirectory, maximumBytes: 7_000_000, maximumRecords: 100,
            binding: binding, expectedKeyID: expectedKeyID, domain: "CJNeedsPlanningSettlement.1", provider: provider)
        try self.init(endpoint: endpoint, binding: binding, credentials: credentials, validate: validate,
            transportFactory: { try ScopedTransport(endpoint: endpoint, profile:.needsPlanning, validate: $0) }, originals: originals, settlements: settlements)
    }
    convenience init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
        validate: @escaping @MainActor () throws -> Void, transport: any ClientTransport,
        originals: ScopedJournal<NeedsPlanningOriginal>, settlements: ScopedJournal<NeedsPlanningSettlement>) throws {
        try self.init(endpoint: endpoint, binding: binding, credentials: credentials, validate: validate,
            transportFactory: { _ in transport }, originals: originals, settlements: settlements)
    }
    private init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
        validate: @escaping @MainActor () throws -> Void,
        transportFactory: @escaping @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport,
        originals: ScopedJournal<NeedsPlanningOriginal>, settlements: ScopedJournal<NeedsPlanningSettlement>) throws {
        guard endpoint.maximumResponseBytes <= 4_000_000, endpoint.maximumRequestBytes <= 32768 else { throw PreviewFailure.invalidInput }
        self.endpoint = endpoint; self.binding = binding; self.credentials = credentials; self.validate = validate
        self.transportFactory = transportFactory; self.originals = originals; self.settlements = settlements
        try check()
    }
    private func check() throws { try validate(); try Task.checkCancellation() }
    public func discover(original: AcceptedTravelMessageSource, validateOriginal: @escaping @MainActor () throws -> Void) async throws -> NeedsPlanningRead {
        try check(); try validateOriginal(); try check()
        let (bytes, trace) = try await exchange(path: "/v1/trip-needs-discovery", query: [
            .init(name: "message_id", value: original.receipt.message_id), .init(name: "run_id", value: original.receipt.run_id)],
            operation: "discoverNeedsPlanningV1", validate: validateOriginal)
        let value = try NeedsPlanningDiscovery.decode(bytes, requestID: trace, reference: original.reference,needsID:original.needsID,needsVersion:original.needsVersion)
        try validateOriginal(); try check()
        return .init(value: value, owner: owner, validate: validateOriginal)
    }
    public func validateRead(_ read: NeedsPlanningRead) throws {
        guard read.owner == owner else { throw PreviewFailure.retired }
        try check(); try read.validate(); try check()
    }
    public func originalActions() throws -> [NeedsPlanningOriginalDisplay] {
        try check()
        let result = try originals.pending().map { original -> NeedsPlanningOriginalDisplay in
            guard let candidate = try original.discovery().candidate else { throw PreviewFailure.invalidResponse }
            return try .init(actionID: original.actionID, kind: original.action.kind, candidate: candidate,discovery:original.discovery())
        }
        try check(); return result
    }
    /// Synchronous button event. A stale view cannot silently choose a newer read.
    public func stage(_ kind: NeedsPlanningAction.Kind, read: NeedsPlanningRead) throws -> NeedsPlanningWork {
        let reservation = UUID(); staging = reservation
        func validateStage() throws {
            guard staging == reservation else { throw PreviewFailure.retired }
            try validateRead(read)
            guard staging == reservation else { throw PreviewFailure.retired }
        }
        try validateStage()
        guard let candidate = read.value.candidate, candidate.status == "pending",
              candidate.expiresAt > Int64(Date().timeIntervalSince1970) else { throw PreviewFailure.conflict }
        let pending = try originals.pending(), settled = try settlements.pending()
        for original in pending {
            guard let previous = try original.discovery().candidate else { throw PreviewFailure.invalidResponse }
            if exact(previous.proposalID, candidate.proposalID) { throw PreviewFailure.unknown }
            if try original.discovery().needsID == read.value.needsID, !settled.contains(where: { exact($0.actionID, original.actionID) }) { throw PreviewFailure.unknown }
        }
        let action = try NeedsPlanningAction.stage(kind: kind, candidate:candidate)
        let original = NeedsPlanningOriginal(actionID: action.actionID, actionUTF8: action.originalUTF8, discoveryUTF8: candidate.discoveryUTF8)
        try originals.append(original, validateBinding: validateStage)
        let proof = try originals.requireOriginal(original)
        try validateStage(); try originals.validateDurability(proof)
        return .init(owner: owner, original: original, read: read, proof: proof)
    }
    public func perform(_ work: NeedsPlanningWork) async throws -> NeedsPlanningResult {
        guard work.owner == owner, !work.started else { throw PreviewFailure.unknown }
        try validateRead(work.read)
        try originals.validateDurability(work.proof)
        work.started = true // never reset, including pre-dispatch/ACK uncertainty
        do {
            let (bytes, trace) = try await exchange(path: "/v1/trip-needs-actions", operation: "actOnNeedsPlanningV1", body: work.original.actionUTF8) {
                try self.validateRead(work.read); try self.originals.validateDurability(work.proof)
            }
            return try settle(work.original, bytes: bytes, trace: trace)
        } catch let failure as NeedsPlanningHTTPRejection {
            // Only the original POST can establish a definitive rejection.
            // GET errors/null and network errors can never create this evidence.
            try validateScopedRejection(failure.bytes, trace: failure.trace, status: failure.status)
            let record = NeedsPlanningSettlement(actionID: work.actionID, original: work.original,
                responseUTF8: failure.bytes, trace: failure.trace, httpStatus: failure.status)
            try settlements.append(record, validateBinding: { try self.validateRead(work.read);try self.originals.validateDurability(work.proof) })
            try originals.validateDurability(work.proof);try validateRead(work.read)
            return .rejected(failure.status)
        }
    }
    public func queryOriginal(_ id: String) async throws -> NeedsPlanningResult {
        try check()
        guard let original = try originals.pending().first(where: { exact($0.actionID, id) }) else { throw PreviewFailure.invalidInput }
        let proof = try originals.requireOriginal(original)
        let (bytes, trace) = try await exchange(path: "/v1/trip-needs-action-receipts", query: [.init(name: "action_id", value: id)], operation: "readNeedsPlanningReceiptV1") {
            try self.originals.validateDurability(proof)
        }
        // Even a previously confirmed original is queried under the current AUTH.
        let result = try settle(original, bytes: bytes, trace: trace)
        if case .unknown = result, let previous = try settlements.pending().first(where: { exact($0.actionID, id) }), previous.httpStatus != 200 {
            try previous.validate(); try check(); return .rejected(previous.httpStatus)
        }
        return result
    }
    private func settle(_ original: NeedsPlanningOriginal, bytes: Data, trace: String) throws -> NeedsPlanningResult {
        guard let c = try original.discovery().candidate else { throw PreviewFailure.invalidResponse }
        let receipt = try NeedsPlanningReceipt.decode(bytes,trace:trace,action:original.action,candidate:c)
        try check()
        guard let receipt else { return .unknown }
        let originalProof = try originals.requireOriginal(original)
        let settlement = NeedsPlanningSettlement(actionID: original.actionID, original: original, responseUTF8: bytes, trace: trace, httpStatus: 200)
        if let prior = try settlements.pending().first(where: { exact($0.actionID, original.actionID) }) {
            guard prior.httpStatus == 200, try prior.receipt().actionID == receipt.actionID, prior.original.actionUTF8 == original.actionUTF8,
                  (try prior.receipt()).committedVersion == receipt.committedVersion else { throw PreviewFailure.invalidResponse }
        } else { try settlements.append(settlement, validateBinding: { try self.check(); try self.originals.validateDurability(originalProof) }) }
        try check(); try originals.validateDurability(originalProof); return .confirmed(receipt)
    }
    public func readFormal(for receipt: NeedsPlanningReceipt) async throws -> StructuredTripRecord? {
        let (bytes, trace) = try await exchange(path: "/v5/trip-structured", query: [.init(name: "trip_id", value: receipt.tripID)], operation: "readNeedsPlanningFormalV1")
        let value = try StructuredTripReadV1.detail(bytes, requestID: trace)
        guard let value, exact(value.tripID, receipt.tripID), let committed = receipt.committedVersion,
              Int64(value.version) >= committed else { throw PreviewFailure.invalidResponse }
        if Int64(value.version) == committed {
            guard let original = try originals.pending().first(where: { exact($0.actionID, receipt.actionID) }),
                  let candidate = try original.discovery().candidate,
                  value.document.originalUTF8 == candidate.content.originalUTF8 else { throw PreviewFailure.invalidResponse }
        }
        try check(); return value
    }
    private func exchange(path: String, query: [URLQueryItem] = [], operation: String, body: Data? = nil,
                          validate original: @escaping @MainActor @Sendable () throws -> Void = {}) async throws -> (Data, String) {
        var components = URLComponents(); components.path = path
        if !query.isEmpty {
            components.queryItems = query
            // C parses application query syntax: a literal plus must remain a plus.
            components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        guard let target = components.string else { throw PreviewFailure.invalidInput }
        try check(); try original(); try check()
        let bearer = try await credentials(binding)
        try check(); try original(); try check()
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw PreviewFailure.unavailable }
        var request = HTTPRequest(method: body == nil ? .get : .post, scheme: nil, authority: nil, path: target)
        request.headerFields[.authorization] = "Bearer " + bearer
        if body != nil { request.headerFields[.contentType] = "application/octet-stream" }
        try original(); try check()
        let transport = try transportFactory { [self] in
            try check(); try original(); try check()
        }
        try original(); try check()
        let (response, responseBody) = try await transport.send(request, body: body.map(HTTPBody.init), baseURL: endpoint.url, operationID: operation)
        try check(); try original(); try check()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw PreviewFailure.invalidResponse }
        let bytes = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try check(); try original(); try check()
        let json = try ScopedWireJSON(bytes, maximumBytes: endpoint.maximumResponseBytes)
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let caches = response.headerFields.filter { $0.name == .cacheControl }
        let media=response.headerFields.filter { $0.name == .contentType }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              json.object["request_id"] as? String == trace, caches.count == 1, caches.first?.value == "no-store",
              media.count==1,media.first?.value.split(separator:";").first?.lowercased()=="application/json" else { throw PreviewFailure.invalidResponse }
        guard response.status.code == 200 else {
            if body != nil, [400, 409].contains(response.status.code) {
                throw NeedsPlanningHTTPRejection(status: response.status.code, bytes: bytes, trace: trace)
            }
            if response.status.code == 409 { throw PreviewFailure.conflict }
            throw PreviewFailure.rejected(response.status.code)
        }
        return (bytes, trace)
    }
}

private struct NeedsPlanningHTTPRejection: Error {
    let status: Int
    let bytes: Data
    let trace: String
}
