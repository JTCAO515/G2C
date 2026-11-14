import CJMessageClient
import Foundation
import HTTPTypes
import Network
import OpenAPIRuntime

/// Uses the signed Beta endpoint and the existing account-bound credential provider.
@MainActor
public final class LioTimelineHTTP {
    public enum Acceptance: Sendable {
        case accepted(conversationID: String)
        case notSent, dailyLimit, rejected
    }

    public struct SavedChat: Sendable, Equatable {
        public let id: String
        public let title: String
    }

    private let scope: StorageScope
    private let lease: Lease
    private let credentials: any MessageCredentialsProvider
    private let transport: NoRedirectTransport
    private let connectivity: LioConnectivity?
    private let firstChatRecovery: MessageRecovery?
    private var firstChatInFlight = false

    public convenience init(endpoint: MessageEndpoint, scope: StorageScope, lease: Lease,
                            credentials: any MessageCredentialsProvider,
                            firstChatRecovery: MessageRecovery? = nil,
                            validate: @escaping @MainActor @Sendable () throws -> Void) throws {
        let transport = try NoRedirectTransport.lioTimeline(endpoint: endpoint, validate: validate)
        self.init(scope: scope, lease: lease, credentials: credentials, transport: transport,
                  monitorNetwork: true, firstChatRecovery: firstChatRecovery)
    }

    init(scope: StorageScope, lease: Lease, credentials: any MessageCredentialsProvider,
         transport: NoRedirectTransport, monitorNetwork: Bool = false,
         firstChatRecovery: MessageRecovery? = nil) {
        self.scope = scope
        self.lease = lease
        self.credentials = credentials
        self.transport = transport
        self.firstChatRecovery = firstChatRecovery
        connectivity = monitorNetwork ? LioConnectivity() : nil
    }

    public func submit(_ original: LioTimelineWire.Send) async throws -> Acceptance {
        if original.startsNewChat, firstChatRecovery == nil {
            throw MessageHTTPFailure.productionActivationUnavailable
        }
        let token = try await bearer()
        if connectivity?.offline == true { return .notSent }
        if original.startsNewChat, let firstChatRecovery {
            return try await submitFirst(original, bearer: token, recovery: firstChatRecovery)
        }
        return try await exchange(original, bearer: token).acceptance
    }

    /// The first accepted original and its verified receipt are stored by
    /// account in the existing encrypted action journal.
    public func savedChats() throws -> [SavedChat] {
        guard let firstChatRecovery else { throw MessageHTTPFailure.productionActivationUnavailable }
        let chats = try recordedFirstActions(in: firstChatRecovery).compactMap { entry -> SavedChat? in
            guard entry.record.phase == .accepted else { return nil }
            guard let receipt = entry.record.receipt else { throw RecoveryError.receiptMismatch }
            return SavedChat(id: try entry.original.confirm(receipt), title: entry.title)
        }
        guard Set(chats.map { Data($0.id.utf8) }).count == chats.count else {
            throw RecoveryError.invalidSnapshot
        }
        return chats.sorted { $0.id.utf8.lexicographicallyPrecedes($1.id.utf8) }
    }

    /// Only absence of an original action or a recorded rejection proves that
    /// a first question can return to a blank composer. An interrupted staged
    /// action remains query-only under MessageRecovery's existing policy.
    public func firstChatCanReturnToDraft(messageID: String) throws -> Bool {
        guard let firstChatRecovery else { throw MessageHTTPFailure.productionActivationUnavailable }
        guard let record = try firstChatRecovery.action(messageID: messageID, lease: lease) else { return true }
        guard try LioTimelineWire.Send.recordedFirst(record.originalUTF8, messageID: record.messageID) != nil else {
            throw RecoveryError.invalidSnapshot
        }
        return record.phase == .notAccepted
    }

    /// Only a signed lookup of the recorded ID and exact digest may resolve a lost first receipt.
    public func reconcileFirstChat(messageID: String? = nil) async throws -> String? {
        guard let firstChatRecovery else { throw MessageHTTPFailure.productionActivationUnavailable }
        guard !firstChatInFlight else { return nil }
        let records = try recordedFirstActions(in: firstChatRecovery)
        if let messageID, let entry = records.first(where: { $0.record.messageID.utf8.elementsEqual(messageID.utf8) }),
           entry.record.phase == .accepted {
            guard let receipt = entry.record.receipt else { throw RecoveryError.receiptMismatch }
            return try entry.original.confirm(receipt)
        }
        let pending = records.filter { $0.record.phase == .queryRequired || $0.record.phase == .notObserved }
        guard pending.count <= 1 else { throw RecoveryError.invalidSnapshot }
        guard let entry = pending.first,
              messageID.map({ entry.record.messageID.utf8.elementsEqual($0.utf8) }) ?? true else { return nil }
        firstChatInFlight = true
        defer { firstChatInFlight = false }
        let token = try await bearer()
        let operation = try firstChatRecovery.beginQuery(messageID: entry.record.messageID, lease: lease)
        let result: FirstChatLookup
        do {
            result = try await readFirstChat(entry.original, inputSHA256: entry.record.inputSHA256, bearer: token)
            try Task.checkCancellation()
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try firstChatRecovery.observeUnknown(operation)
            throw error
        }
        switch result {
        case .missing:
            try firstChatRecovery.observeNotObserved(operation)
            return nil
        case .conflict:
            try firstChatRecovery.observeIntegrityError(operation)
            return nil
        case .confirmed(let id, let receipt):
            try firstChatRecovery.observeReceipt(operation, messageID: entry.record.messageID,
                                                inputSHA256: entry.record.inputSHA256, receipt: receipt)
            return id
        }
    }

    private enum FirstChatLookup { case missing, conflict, confirmed(String, Data) }

    private func readFirstChat(_ original: LioTimelineWire.Send, inputSHA256: String,
                               bearer: String) async throws -> FirstChatLookup {
        let (response, body) = try await transport.readLioFirstReceipt(original, inputSHA256: inputSHA256, bearer: bearer)
        let bytes = try await json(response, body, limit: 65_536)
        switch response.status.code {
        case 200:
            guard let result = try original.confirmLookup(bytes) else { return .missing }
            return .confirmed(result.id, result.receipt)
        case 409:
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "unavailable" else {
                throw MessageHTTPFailure.invalidResponse
            }
            return .conflict
        default:
            throw MessageHTTPFailure.exchangeUnknown
        }
    }

    private func submitFirst(_ original: LioTimelineWire.Send, bearer token: String,
                             recovery: MessageRecovery) async throws -> Acceptance {
        guard !firstChatInFlight else { throw RecoveryError.queryOnly }
        let previous = try recordedFirstActions(in: recovery)
        guard !previous.contains(where: { $0.record.phase != .accepted && $0.record.phase != .notAccepted }) else {
            throw RecoveryError.queryOnly
        }
        firstChatInFlight = true
        defer { firstChatInFlight = false }
        try recovery.stage(messageID: original.messageID, originalUTF8: original.originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: original.messageID, lease: lease)
        let outcome: SendOutcome
        do {
            outcome = try await exchange(original, bearer: token)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try recovery.observeUnknown(submission.operation)
            throw error
        }
        switch outcome {
        case .accepted(_, let receipt):
            guard let record = try recovery.action(messageID: original.messageID, lease: lease) else {
                throw RecoveryError.receiptMismatch
            }
            try recovery.observeReceipt(submission.operation, messageID: original.messageID,
                                        inputSHA256: record.inputSHA256, receipt: receipt)
        case .rejected(let status, let proof):
            try recovery.observeSubmissionRejection(submission.operation, httpStatus: status, responseUTF8: proof)
        }
        return outcome.acceptance
    }

    private func recordedFirstActions(in recovery: MessageRecovery) throws -> [(record: ActionRecord, original: LioTimelineWire.Send, title: String)] {
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        return try projection.actions.compactMap { item in
            guard let record = try recovery.action(messageID: item.messageID, lease: lease) else {
                throw RecoveryError.invalidSnapshot
            }
            guard let parsed = try LioTimelineWire.Send.recordedFirst(record.originalUTF8, messageID: record.messageID) else {
                return nil
            }
            return (record, parsed.original, parsed.title)
        }
    }

    private enum SendOutcome {
        case accepted(String, Data)
        case rejected(Int, Data)

        var acceptance: Acceptance {
            switch self {
            case .accepted(let id, _): .accepted(conversationID: id)
            case .rejected(let status, _): status == 429 ? .dailyLimit : .rejected
            }
        }
    }

    private func exchange(_ original: LioTimelineWire.Send, bearer token: String) async throws -> SendOutcome {
        let (response, body) = try await transport.sendLio(original, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        let status = response.status.code
        // The v2 route uses 400 for invalid input before acceptance. Access
        // failures can also come from reconciling an earlier uncertain commit.
        if status == 429 || (status == 400 && original.startsNewChat) {
            let expected = status == 429 ? "quota" : "unavailable"
            if original.version == .v4 {
                try LioNative4Envelope.rejection(bytes, expected: expected)
            } else {
                try validateUnambiguousJSON(bytes)
                guard try JSONDecoder().decode(Failure.self, from: bytes).failure == expected else {
                    throw MessageHTTPFailure.invalidResponse
                }
            }
            return .rejected(status, bytes)
        }
        guard status == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        return .accepted(try original.confirm(bytes), bytes)
    }

    public func timeline(conversationID: String? = nil, before: String? = nil,
                         version: LioTimelineWire.Version = .v1) async throws -> LioTimelineWire.Page {
        let token = try await bearer()
        let (response, body) = try await transport.readLio(conversationID: conversationID, before: before, bearer: token, version: version)
        guard response.status.code == 200 else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await json(response, body, limit: 4_500_000)
        let page = try LioTimelineWire.decodePage(bytes, for: conversationID, version: version)
        if let before, page.messages.contains(where: { $0.id.utf8.elementsEqual(before.utf8) }) {
            throw MessageHTTPFailure.invalidResponse
        }
        return page
    }

    /// Explicit native4 read, preserving its typed presentation instead of using the legacy page decoder.
    public func exploration(conversationID: String? = nil, before: String? = nil) async throws -> LioExplorationWire.Page {
        let token = try await bearer()
        let (response, body) = try await transport.readLio(conversationID: conversationID, before: before,
                                                         bearer: token, version: .v4)
        guard response.status.code == 200 else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await json(response, body, limit: 4_500_000)
        let page = try LioExplorationWire.decodePage(bytes, for: conversationID)
        if let before, page.messages.contains(where: { $0.id.utf8.elementsEqual(before.utf8) }) {
            throw MessageHTTPFailure.invalidResponse
        }
        return page
    }

    func tripHistory(before: String?, conversationID: String? = nil) async throws -> LioTripHistoryWire.Page {
        let token = try await bearer()
        let (response, body) = try await transport.readLioTrip(before: before, bearer: token, conversationID: conversationID)
        guard response.status.code == 200 else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await json(response, body, limit: 4_500_000)
        return try LioTripHistoryWire.decodePage(bytes, before: before, conversationID: conversationID)
    }

    func submitUndo(_ undo: LioTripHistoryWire.Undo) async throws -> LioTripHistoryClient.SubmissionResult {
        let token = try await bearer()
        let (response, body) = try await transport.sendLioUndo(undo, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        switch response.status.code {
        case 200:
            guard try undo.committed(bytes) else { throw MessageHTTPFailure.exchangeUnknown }
            return .committed(bytes)
        case 409:
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "unavailable" else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            return .conflict(bytes)
        default:
            throw MessageHTTPFailure.exchangeUnknown
        }
    }

    func readUndo(_ undo: LioTripHistoryWire.Undo) async throws -> Data? {
        let token = try await bearer()
        let (response, body) = try await transport.readLioUndo(undo, bearer: token)
        guard response.status.code == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        let bytes = try await json(response, body, limit: 65_536)
        return try undo.committed(bytes) ? bytes : nil
    }

    func submitMemoryChoice(_ action: LioMemoryWire.Action) async throws -> LioMemoryActionsClient.SubmissionResult {
        let token = try await bearer()
        let (response, body) = try await transport.sendLioMemoryChoice(action, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        switch response.status.code {
        case 200: return .receipt(bytes)
        case 409:
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "unavailable" else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            return .conflict(bytes)
        default:
            throw MessageHTTPFailure.exchangeUnknown
        }
    }

    func readMemoryChoice(_ action: LioMemoryWire.Action) async throws -> Data {
        let token = try await bearer()
        let (response, body) = try await transport.readLioMemoryChoice(action, bearer: token)
        guard response.status.code == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        return try await json(response, body, limit: 65_536)
    }

    private func bearer() async throws -> String {
        guard let token = try await credentials.bearer(for: scope, lease: lease),
              !token.isEmpty, !token.contains(","), !token.contains(where: \.isWhitespace) else {
            throw MessageHTTPFailure.credentialsUnavailable
        }
        return token
    }

    private func json(_ response: HTTPResponse, _ body: HTTPBody?, limit: Int) async throws -> Data {
        guard response.headerFields[.contentType]?.split(separator: ";").first?.lowercased() == "application/json",
              let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: limit)
        try Task.checkCancellation()
        return bytes
    }

    private struct Failure: Decodable { let failure: String }
}


/// A known absence of a network path before a POST permits an explicit resend.
/// Errors returned after invoking the transport remain uncertain.
@MainActor
private final class LioConnectivity {
    private let monitor = NWPathMonitor()
    private(set) var offline = false

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let offline = path.status == .unsatisfied
            Task { @MainActor in self?.offline = offline }
        }
        monitor.start(queue: DispatchQueue(label: "g2c.lio.connectivity"))
    }

    deinit { monitor.cancel() }
}
