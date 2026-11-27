import Foundation

/// The undo of an automatic save (#1994, ADR-0012; `LIO-answer-rich.1` `trip_receipt`).
///
/// Two requests share `POST /v4/lio/trip-undos` and `GET /v4/lio/trip-undo-receipts`, told apart by `version`:
/// `LIO-trip-undo.4` restores the version before the committed one, `LIO-trip-undo.5` marks the trip a save created as
/// withdrawn. Both answer `LIO-trip-undo-receipt.4`. The App builds a request from a receipt's `undo` and nothing else:
/// the action id is the server's (`undo-` and 40 hex characters, the same on every device, so a replay is safe), the target
/// is the receipt's own snapshot, and the conversation is the one the receipt was read in. No place name, user text, device
/// detail or client-made marker is in a request, and nothing here is logged.
public enum LioTripUndoWire {
    public static let restoreVersion = "LIO-trip-undo.4"
    public static let withdrawVersion = "LIO-trip-undo.5"
    public static let receiptVersion = "LIO-trip-undo-receipt.4"
    /// The server refuses a longer body or target.
    public static let maximumRequestBytes = 2048

    public struct Request: Sendable, Equatable {
        public let kind: LioTimelineWire.TripReceipt.Undo.Kind
        public let actionID: String
        public let conversationID: String
        public let target: LioTimelineWire.TripReceipt.UndoTarget
        /// The exact JSON body of the POST.
        public let body: Data
        /// The target as compact JSON, the value of the receipt query's `target`.
        let targetJSON: String

        /// The request for the undo the receipt offers, or nil when it offers none (not a saved receipt, not `available`,
        /// a kind and target that do not fit, or a conversation id that is not one).
        public init?(receipt: LioTimelineWire.TripReceipt, conversationID: String) {
            guard receipt.status == .saved, let undo = receipt.undo, undo.state == .available,
                  let kind = undo.kind, let actionID = undo.actionID, let target = undo.target,
                  LioTimelineWire.validUndoActionID(actionID),
                  LioTimelineWire.validConversationID(conversationID),
                  (kind == .restore) == (target.restore != nil) else { return nil }
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            guard let targetBytes = try? encoder.encode(TargetBody(target)),
                  let targetJSON = String(data: targetBytes, encoding: .utf8),
                  let body = try? encoder.encode(Body(version: kind == .restore ? LioTripUndoWire.restoreVersion : LioTripUndoWire.withdrawVersion,
                                                     actionID: actionID, conversationID: conversationID, target: TargetBody(target))),
                  body.count <= LioTripUndoWire.maximumRequestBytes, targetBytes.count <= LioTripUndoWire.maximumRequestBytes
            else { return nil }
            self.kind = kind
            self.actionID = actionID
            self.conversationID = conversationID
            self.target = target
            self.body = body
            self.targetJSON = targetJSON
        }

        /// `LIO-trip-undo.4` or `.5`.
        public var version: String { kind == .restore ? LioTripUndoWire.restoreVersion : LioTripUndoWire.withdrawVersion }

        /// The receipt query: the same values as the POST, `target` as JSON, and `version` only for `.5` (without it the
        /// server reads `.4`).
        var query: [URLQueryItem] {
            var items = [URLQueryItem(name: "action_id", value: actionID), URLQueryItem(name: "target", value: targetJSON),
                         URLQueryItem(name: "conversation_id", value: conversationID)]
            if kind == .withdrawCreated { items.append(URLQueryItem(name: "version", value: LioTripUndoWire.withdrawVersion)) }
            return items
        }
    }

    /// What the server's answer to one request says, before the App decides what to show.
    enum Reply: Sendable, Equatable {
        /// 200 with `committed: true`.
        case committed
        /// 200 with `committed: false`: nothing was written.
        case notCommitted
        /// 409: the trip is no longer what the target says (a newer version exists, or the trip is gone).
        case changed
        /// 403: the server refused it, which is how it says the 24 hours are over.
        case refused
        /// Any other status, or a body that is not the contract's: the outcome is not known.
        case other
    }

    /// The reply to a 200: `LIO-trip-undo-receipt.4` with exactly its four fields, naming this request's action and
    /// conversation.
    static func committed(_ data: Data, for request: Request) throws -> Bool {
        guard data.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
        var reader = StrictJSON(bytes: Array(data))
        let root = try reader.document()
        _ = try CardJSON.fields(root, "version conversation_id action_id committed")
        let receipt = try JSONDecoder().decode(Receipt.self, from: data)
        guard receipt.version == receiptVersion, receipt.actionID == request.actionID,
              receipt.conversationID == request.conversationID else { throw MessageHTTPFailure.invalidResponse }
        return receipt.committed
    }

    private struct Body: Encodable {
        let version: String
        let actionID: String
        let conversationID: String
        let target: TargetBody
        enum CodingKeys: String, CodingKey { case version, actionID = "action_id", conversationID = "conversation_id", target }
    }

    private struct TargetBody: Encodable {
        let target: LioTimelineWire.TripReceipt.UndoTarget
        init(_ target: LioTimelineWire.TripReceipt.UndoTarget) { self.target = target }
        enum CodingKeys: String, CodingKey {
            case tripID = "trip_id", expectedVersion = "expected_version", originalHash = "original_hash"
            case contentVersion = "content_version", restoreVersion = "restore_version", restoreHash = "restore_hash"
            case restoreContentVersion = "restore_content_version"
        }
        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(target.tripID, forKey: .tripID)
            try c.encode(target.expectedVersion, forKey: .expectedVersion)
            try c.encode(target.originalHash, forKey: .originalHash)
            try c.encode(target.contentVersion, forKey: .contentVersion)
            if let restore = target.restore {
                try c.encode(restore.version, forKey: .restoreVersion)
                try c.encode(restore.hash, forKey: .restoreHash)
                try c.encode(restore.contentVersion, forKey: .restoreContentVersion)
            }
        }
    }

    private struct Receipt: Decodable {
        let version: String
        let actionID: String
        let conversationID: String
        let committed: Bool
        enum CodingKeys: String, CodingKey {
            case version, actionID = "action_id", conversationID = "conversation_id", committed
        }
    }
}

/// Sends the undo a receipt offers and reads back what the server did. The server decides everything: the 24 hours, the
/// current version, whether the trip is still the receipt's. This only carries the request, never twice at once for one
/// action, and never claims a result the server did not give.
///
/// An answer that is not known (no connection, a 5xx, a body that is not the contract's) is not a failure: the same action
/// id is asked again through the receipt query, which says whether the undo was committed. A fresh id is never made.
@MainActor
public final class LioTripUndoClient {
    public enum Outcome: Sendable, Equatable {
        /// The server committed the undo (the receipt query said so, or the POST did).
        case undone
        /// The trip changed since the save: a newer version exists, so this save can no longer be undone.
        case superseded
        /// The server refused: the 24 hours are over.
        case expired
        /// The server answered and nothing was written. Asking again is allowed.
        case notDone
        /// No answer that can be trusted, also not from the receipt query. Nothing is known; ask again with the same id.
        case unknown
        /// This action is already being sent: nothing was sent now.
        case inFlight
    }

    private let send: @MainActor (LioTripUndoWire.Request) async throws -> LioTripUndoWire.Reply
    private let read: @MainActor (LioTripUndoWire.Request) async throws -> LioTripUndoWire.Reply
    private var inFlight: Set<String> = []

    public convenience init(timeline: LioTimelineHTTP) {
        self.init(send: { try await timeline.submitTripUndo($0) }, read: { try await timeline.readTripUndoReceipt($0) })
    }

    init(send: @escaping @MainActor (LioTripUndoWire.Request) async throws -> LioTripUndoWire.Reply,
         read: @escaping @MainActor (LioTripUndoWire.Request) async throws -> LioTripUndoWire.Reply) {
        self.send = send
        self.read = read
    }

    /// Whether this action is being sent right now.
    public func isSending(_ actionID: String) -> Bool { inFlight.contains(actionID) }

    /// POST the undo. If the answer is not known, ask the receipt query for the same action before saying anything.
    public func undo(_ request: LioTripUndoWire.Request) async -> Outcome {
        guard inFlight.insert(request.actionID).inserted else { return .inFlight }
        defer { inFlight.remove(request.actionID) }
        let reply: LioTripUndoWire.Reply
        do { reply = try await send(request) } catch is CancellationError { return .unknown } catch { reply = .other }
        if reply == .other { return await ask(request) }
        return Self.outcome(reply)
    }

    /// Ask only: has this action been committed? For an undo whose answer was not known, and for a retry.
    public func confirm(_ request: LioTripUndoWire.Request) async -> Outcome {
        guard inFlight.insert(request.actionID).inserted else { return .inFlight }
        defer { inFlight.remove(request.actionID) }
        return await ask(request)
    }

    private func ask(_ request: LioTripUndoWire.Request) async -> Outcome {
        do { return Self.outcome(try await read(request)) } catch { return .unknown }
    }

    private static func outcome(_ reply: LioTripUndoWire.Reply) -> Outcome {
        switch reply {
        case .committed: .undone
        case .notCommitted: .notDone
        case .changed: .superseded
        case .refused: .expired
        case .other: .unknown
        }
    }
}
