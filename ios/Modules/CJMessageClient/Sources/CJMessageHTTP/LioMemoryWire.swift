import Foundation

public enum LioMemoryWire {
    public struct Tag: Decodable, Hashable, Identifiable, Sendable {
        public let id: String
        public let text: String
        let kind: Kind
        fileprivate let target: String

        enum Kind: String, Decodable, Hashable, Sendable { case fact, preference }

        var isValid: Bool {
            LioTimelineWire.validMessageID(id)
                && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !text.utf8.contains(0)
                && LioMemoryWire.validTarget(target)
        }
    }

    public enum Choice: String, Codable, Sendable { case remember, dismiss }

    public static let maximumRequestBytes = 262_144 + 4096

    private static func validTarget(_ target: String) -> Bool {
        !target.isEmpty && target.utf8.count <= 262_144 && target.utf8.allSatisfy {
            (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95
        }
    }

    struct Action: Sendable {
        static let idPrefix = "lio-memory-"
        let actionID: String
        let choice: Choice
        private let target: String
        let originalUTF8: Data

        init(choice: Choice, tag: Tag) throws {
            guard tag.isValid else { throw MessageHTTPFailure.invalidConfiguration }
            let id = Self.idPrefix + UUID().uuidString.lowercased()
            let request = Request(version: "LIO-memory-action.1", actionID: id, operation: choice, target: tag.target)
            actionID = id
            self.choice = choice
            target = tag.target
            originalUTF8 = try JSONEncoder().encode(request)
        }

        init(originalUTF8: Data, expectedActionID: String) throws {
            guard originalUTF8.count <= LioMemoryWire.maximumRequestBytes else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            try validateUnambiguousJSON(originalUTF8)
            let request = try JSONDecoder().decode(Request.self, from: originalUTF8)
            guard request.version == "LIO-memory-action.1", request.actionID == expectedActionID,
                  request.actionID.hasPrefix(Self.idPrefix),
                  UUID(uuidString: String(request.actionID.dropFirst(Self.idPrefix.count))) != nil,
                  LioMemoryWire.validTarget(request.target) else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            actionID = request.actionID
            choice = request.operation
            target = request.target
            self.originalUTF8 = originalUTF8
        }

        func matches(_ tag: Tag) -> Bool { target == tag.target }

        func outcome(_ data: Data) throws -> LioMemoryActionsClient.State {
            guard data.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
            try validateUnambiguousJSON(data)
            let receipt = try JSONDecoder().decode(Receipt.self, from: data)
            guard receipt.version == "LIO-memory-action-receipt.1", receipt.actionID == actionID else {
                throw MessageHTTPFailure.invalidResponse
            }
            switch (choice, receipt.status) {
            case (_, .pending): return .pending
            case (.remember, .remembered): return .remembered
            case (.dismiss, .dismissed): return .dismissed
            default: throw MessageHTTPFailure.invalidResponse
            }
        }
    }

    private struct Request: Codable {
        let version: String
        let actionID: String
        let operation: Choice
        let target: String
        enum CodingKeys: String, CodingKey { case version, actionID = "action_id", operation, target }
    }

    private struct Receipt: Decodable {
        enum Status: String, Decodable { case remembered, dismissed, pending }
        let version: String
        let actionID: String
        let status: Status
        enum CodingKeys: String, CodingKey { case version, actionID = "action_id", status }
    }
}
