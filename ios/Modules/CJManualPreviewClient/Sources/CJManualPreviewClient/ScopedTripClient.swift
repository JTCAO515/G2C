import Foundation
import Observation
import CJTripClient
import CJMessageHTTP
import CJMessageKeys
import OpenAPIRuntime
import HTTPTypes

@MainActor public final class ScopedCandidateRead {
    public let value: ScopedDiscovery
    fileprivate let owner: UUID
    fileprivate let validate: @MainActor () throws -> Void
    fileprivate init(value: ScopedDiscovery, owner: UUID, validate: @escaping @MainActor () throws -> Void) {
        self.value = value; self.owner = owner; self.validate = validate
    }
}
@MainActor public final class ScopedDecisionWork {
    public let actionID: String
    fileprivate let owner: UUID
    fileprivate let original: ScopedOriginal
    fileprivate let read: ScopedCandidateRead
    fileprivate let proof: ScopedJournal<ScopedOriginal>.Durability
    fileprivate var started = false
    fileprivate init(owner: UUID, original: ScopedOriginal, read: ScopedCandidateRead, proof: ScopedJournal<ScopedOriginal>.Durability) {
        self.owner = owner; self.original = original; self.read = read; self.proof = proof; actionID = original.actionID
    }
}
public struct ScopedOriginalDisplay: Identifiable, Sendable {
    public var id: String { actionID }
    public let actionID: String
    public let kind: ScopedAction.Kind
    public let candidate: ScopedCandidate
}
public enum ScopedDecisionResult: Sendable {
    case confirmed(ScopedActionReceipt), unknown, rejected(Int)
}

/// One account/session lifetime. New writes require an actual protected read,
/// one explicit choice and durable bytes. Existing originals expose GET only.
@MainActor public final class ScopedTripClient {
    private let endpoint: MessageEndpoint
    private let binding: TripBinding
    private let credentials: TripCredentialCallback
    private let validate: @MainActor () throws -> Void
    private let transport: any ClientTransport
    private let originals: ScopedJournal<ScopedOriginal>
    private let settlements: ScopedJournal<ScopedSettlement>
    private let owner = UUID()
    private var staging = UUID()
    public convenience init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
        validate: @escaping @MainActor () throws -> Void, directory: URL, receiptDirectory: URL,
        expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        let originals = try ScopedJournal<ScopedOriginal>(directory: directory, maximumBytes: 6_000_000, maximumRecords: 100,
            binding: binding, expectedKeyID: expectedKeyID, domain: "CJScopedOriginal.1", provider: provider)
        let settlements = try ScopedJournal<ScopedSettlement>(directory: receiptDirectory, maximumBytes: 7_000_000, maximumRecords: 100,
            binding: binding, expectedKeyID: expectedKeyID, domain: "CJScopedSettlement.1", provider: provider)
        try self.init(endpoint: endpoint, binding: binding, credentials: credentials, validate: validate,
            transport: ScopedTransport(endpoint: endpoint), originals: originals, settlements: settlements)
    }
    init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
        validate: @escaping @MainActor () throws -> Void, transport: any ClientTransport,
        originals: ScopedJournal<ScopedOriginal>, settlements: ScopedJournal<ScopedSettlement>) throws {
        guard endpoint.maximumResponseBytes <= 4_000_000, endpoint.maximumRequestBytes <= 32768 else { throw PreviewFailure.invalidInput }
        self.endpoint = endpoint; self.binding = binding; self.credentials = credentials; self.validate = validate
        self.transport = transport; self.originals = originals; self.settlements = settlements
        try check()
    }
    private func check() throws { try validate(); try Task.checkCancellation() }
    public func discover(original: MessageEditReference, validateOriginal: @escaping @MainActor () throws -> Void) async throws -> ScopedCandidateRead {
        try check(); try validateOriginal(); try check()
        let (bytes, trace) = try await exchange(path: "/v1/trip-scoped-discovery", query: [
            .init(name: "message_id", value: original.messageID), .init(name: "run_id", value: original.runID)],
            operation: "discoverScopedTripV1", validate: validateOriginal)
        let value = try ScopedDiscovery.decode(bytes, requestID: trace, original: original)
        try validateOriginal(); try check()
        return .init(value: value, owner: owner, validate: validateOriginal)
    }
    public func validateRead(_ read: ScopedCandidateRead) throws {
        guard read.owner == owner else { throw PreviewFailure.retired }
        try check(); try read.validate(); try check()
    }
    public func originalActions() throws -> [ScopedOriginalDisplay] {
        try check()
        let result = try originals.pending().map { original -> ScopedOriginalDisplay in
            guard let candidate = try original.discovery().candidate else { throw PreviewFailure.invalidResponse }
            return try .init(actionID: original.actionID, kind: original.action.kind, candidate: candidate)
        }
        try check(); return result
    }
    /// Synchronous button event. A stale view cannot silently choose a newer read.
    public func stage(_ kind: ScopedAction.Kind, read: ScopedCandidateRead) throws -> ScopedDecisionWork {
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
            if exact(previous.tripID, candidate.tripID), !settled.contains(where: { exact($0.actionID, original.actionID) }) { throw PreviewFailure.unknown }
        }
        let action = try ScopedAction.stage(kind: kind, proposalID: candidate.proposalID, candidateHash: candidate.candidateHash)
        let original = ScopedOriginal(actionID: action.actionID, actionUTF8: action.originalUTF8, discoveryUTF8: candidate.discoveryUTF8)
        try originals.append(original, validateBinding: validateStage)
        let proof = try originals.requireOriginal(original)
        try validateStage(); try originals.validateDurability(proof)
        return .init(owner: owner, original: original, read: read, proof: proof)
    }
    public func perform(_ work: ScopedDecisionWork) async throws -> ScopedDecisionResult {
        guard work.owner == owner, !work.started else { throw PreviewFailure.unknown }
        try validateRead(work.read)
        try originals.validateDurability(work.proof)
        work.started = true // never reset, including pre-dispatch/ACK uncertainty
        do {
            let (bytes, trace) = try await exchange(path: "/v1/trip-scoped-actions", operation: "actOnScopedTripV1", body: work.original.actionUTF8) {
                try self.validateRead(work.read); try self.originals.validateDurability(work.proof)
            }
            return try settle(work.original, bytes: bytes, trace: trace)
        } catch let failure as ScopedHTTPRejection {
            // Only the original POST can establish a definitive rejection.
            // GET errors/null and network errors can never create this evidence.
            try validateScopedRejection(failure.bytes, trace: failure.trace, status: failure.status)
            let record = ScopedSettlement(actionID: work.actionID, original: work.original,
                responseUTF8: failure.bytes, trace: failure.trace, httpStatus: failure.status)
            try settlements.append(record, validateBinding: { try self.validateRead(work.read) })
            return .rejected(failure.status)
        }
    }
    public func queryOriginal(_ id: String) async throws -> ScopedDecisionResult {
        try check()
        guard let original = try originals.pending().first(where: { exact($0.actionID, id) }) else { throw PreviewFailure.invalidInput }
        let proof = try originals.requireOriginal(original)
        let (bytes, trace) = try await exchange(path: "/v1/trip-scoped-action-receipts", query: [.init(name: "action_id", value: id)], operation: "readScopedTripReceiptV1") {
            try self.originals.validateDurability(proof)
        }
        // Even a previously confirmed original is queried under the current AUTH.
        let result = try settle(original, bytes: bytes, trace: trace)
        if case .unknown = result, let previous = try settlements.pending().first(where: { exact($0.actionID, id) }), previous.httpStatus != 200 {
            try previous.validate(); try check(); return .rejected(previous.httpStatus)
        }
        return result
    }
    private func settle(_ original: ScopedOriginal, bytes: Data, trace: String) throws -> ScopedDecisionResult {
        guard let c = try original.discovery().candidate else { throw PreviewFailure.invalidResponse }
        let receipt = try ScopedActionReceipt.decode(bytes, requestID: trace, original: original.action,
            tripID: c.tripID, expectedVersion: c.expectedVersion, maximumBytes: 65536)
        try check()
        guard let receipt else { return .unknown }
        let settlement = ScopedSettlement(actionID: original.actionID, original: original, responseUTF8: bytes, trace: trace, httpStatus: 200)
        if let prior = try settlements.pending().first(where: { exact($0.actionID, original.actionID) }) {
            guard prior.httpStatus == 200, try prior.receipt().actionID == receipt.actionID, prior.original.actionUTF8 == original.actionUTF8,
                  (try prior.receipt()).committedVersion == receipt.committedVersion else { throw PreviewFailure.invalidResponse }
        } else { try settlements.append(settlement, validateBinding: { try self.check() }) }
        try check(); return .confirmed(receipt)
    }
    public func readFormal(for receipt: ScopedActionReceipt) async throws -> StructuredTripRecord? {
        let (bytes, trace) = try await exchange(path: "/v5/trip-structured", query: [.init(name: "trip_id", value: receipt.tripID)], operation: "readScopedFormalTripV1")
        let value = try StructuredTripReadV1.detail(bytes, requestID: trace)
        guard value?.tripID == receipt.tripID else { throw PreviewFailure.invalidResponse }
        try check(); return value
    }
    private func exchange(path: String, query: [URLQueryItem] = [], operation: String, body: Data? = nil,
                          validate original: @escaping @MainActor () throws -> Void = {}) async throws -> (Data, String) {
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
        let (response, responseBody) = try await transport.send(request, body: body.map(HTTPBody.init), baseURL: endpoint.url, operationID: operation)
        try check(); try original(); try check()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw PreviewFailure.invalidResponse }
        let bytes = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try check(); try original(); try check()
        let json = try ScopedWireJSON(bytes, maximumBytes: endpoint.maximumResponseBytes)
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let caches = response.headerFields.filter { $0.name == .cacheControl }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              json.object["request_id"] as? String == trace, caches.count == 1, caches.first?.value == "no-store" else { throw PreviewFailure.invalidResponse }
        guard response.status.code == 200 else {
            if body != nil, [400, 409].contains(response.status.code) {
                throw ScopedHTTPRejection(status: response.status.code, bytes: bytes, trace: trace)
            }
            if response.status.code == 409 { throw PreviewFailure.conflict }
            throw PreviewFailure.rejected(response.status.code)
        }
        return (bytes, trace)
    }
}

private struct ScopedHTTPRejection: Error {
    let status: Int
    let bytes: Data
    let trace: String
}
