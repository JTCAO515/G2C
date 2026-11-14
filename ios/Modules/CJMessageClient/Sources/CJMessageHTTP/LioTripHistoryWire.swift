import Foundation

public enum LioTripHistoryWire {
    public struct Target: Equatable, Sendable {
        fileprivate let encoded: String
        let conversationID: String?
    }

    public struct Page: Sendable {
        public let current: LioTimelineWire.SavedTrip?
        public let history: [LioTimelineWire.SavedTrip]
        public let undoTarget: Target?
        public let nextBefore: String?
    }

    static func validCursor(_ cursor: String) -> Bool {
        guard let value = Int64(cursor), value > 0 else { return false }
        return String(value) == cursor
    }

    private static func validTarget(_ target: String) -> Bool {
        !target.isEmpty && target.utf8.count <= 512 && target.utf8.allSatisfy {
            (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95
        }
    }

    public static func decodePage(_ data: Data, before: String? = nil, conversationID: String? = nil) throws -> Page {
        guard data.count <= 4_500_000 else { throw MessageHTTPFailure.invalidResponse }
        try validateUnambiguousJSON(data)
        let page = try JSONDecoder().decode(History.self, from: data)
        let version = conversationID == nil ? 1 : 2
        guard page.version == "LIO-trip-history.\(version)",
              conversationID.map({ LioTimelineWire.validConversationID($0) && page.conversationID == $0 }) ?? true,
              page.history.count <= (page.current == nil ? 10 : 9),
              page.nextBefore.map(validCursor) ?? true,
              page.undoTarget.map(validTarget) ?? true,
              before == nil || (page.current == nil && page.undoTarget == nil),
              before != nil || page.current != nil || (page.history.isEmpty && page.nextBefore == nil),
              page.undoTarget == nil || (page.current != nil && !page.history.isEmpty),
              page.nextBefore == nil || !page.history.isEmpty else {
            throw MessageHTTPFailure.invalidResponse
        }
        if let before, let next = page.nextBefore {
            guard let requested = Int64(before), let returned = Int64(next), returned < requested else {
                throw MessageHTTPFailure.invalidResponse
            }
        }
        let cards = (page.current.map { [$0] } ?? []) + page.history
        guard cards.allSatisfy(LioTimelineWire.validSavedTrip),
              Set(cards.map(\.id)).count <= 1 else { throw MessageHTTPFailure.invalidResponse }
        return Page(current: page.current, history: page.history,
                    undoTarget: page.undoTarget.map { Target(encoded: $0, conversationID: conversationID) },
                    nextBefore: page.nextBefore)
    }

    struct Undo: Sendable {
        static let idPrefix = "lio-undo-"
        let actionID: String
        let target: String
        let conversationID: String?
        let originalUTF8: Data
        var version: Int { conversationID == nil ? 1 : 2 }

        init(target: Target) throws {
            let actionID = Self.idPrefix + UUID().uuidString.lowercased()
            self.actionID = actionID
            self.target = target.encoded
            conversationID = target.conversationID
            let payload = Request(version: "LIO-trip-undo.\(target.conversationID == nil ? 1 : 2)",
                                  actionID: actionID, target: target.encoded, conversationID: target.conversationID)
            originalUTF8 = try JSONEncoder().encode(payload)
        }

        init(originalUTF8: Data, expectedActionID: String) throws {
            guard originalUTF8.count <= 1024 else { throw MessageHTTPFailure.invalidConfiguration }
            try validateUnambiguousJSON(originalUTF8)
            let request = try JSONDecoder().decode(Request.self, from: originalUTF8)
            let version = request.conversationID == nil ? 1 : 2
            guard request.version == "LIO-trip-undo.\(version)", request.actionID == expectedActionID,
                  request.conversationID.map(LioTimelineWire.validConversationID) ?? true,
                  request.actionID.hasPrefix(Self.idPrefix),
                  UUID(uuidString: String(request.actionID.dropFirst(Self.idPrefix.count))) != nil,
                  LioTripHistoryWire.validTarget(request.target) else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            actionID = request.actionID
            target = request.target
            conversationID = request.conversationID
            self.originalUTF8 = originalUTF8
        }

        func committed(_ data: Data) throws -> Bool {
            guard data.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
            try validateUnambiguousJSON(data)
            let receipt = try JSONDecoder().decode(Receipt.self, from: data)
            guard receipt.version == "LIO-trip-undo-receipt.\(version)", receipt.actionID == actionID,
                  conversationID.map({ receipt.conversationID == $0 }) ?? true else {
                throw MessageHTTPFailure.invalidResponse
            }
            return receipt.committed
        }
    }

    private struct History: Decodable {
        let version: String
        let conversationID: String?
        let current: LioTimelineWire.SavedTrip?
        let history: [LioTimelineWire.SavedTrip]
        let undoTarget: String?
        let nextBefore: String?
        enum CodingKeys: String, CodingKey {
            case version, current, history, undoTarget = "undo_target", nextBefore = "next_before"
            case conversationID = "conversation_id"
        }
    }

    private struct Request: Codable {
        let version: String
        let actionID: String
        let target: String
        let conversationID: String?
        enum CodingKeys: String, CodingKey {
            case version, actionID = "action_id", target, conversationID = "conversation_id"
        }
    }

    private struct Receipt: Decodable {
        let version: String
        let actionID: String
        let committed: Bool
        let conversationID: String?
        enum CodingKeys: String, CodingKey {
            case version, actionID = "action_id", committed, conversationID = "conversation_id"
        }
    }
}
